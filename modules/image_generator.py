"""
modules/image_generator.py — ComfyUI REST API: 8 custom scene images + thumbnail per short.

PROMPT STRATEGY (two-tier):
  1. PRIMARY — Cerebras reads the actual script and writes 8 bespoke ComfyUI
     image prompts tailored to that story's exact setting, characters, mood,
     and narrative arc.  This makes every short visually unique.
  2. FALLBACK — If Cerebras is unavailable (quota / network), the system falls
     back to the channel-specific narrative-arc templates with context injection.

8 scenes cover the full story arc (hook → setup → conflict → climax → resolution).
"""

import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from config import (
    CEREBRAS_API_KEY, CEREBRAS_MODEL,
    CEREBRAS_TEMP_STRUCTURED, CEREBRAS_MAX_TOKENS_PROMPTS,
    COMFYUI_URL, COMFYUI_URLS, CHANNELS,
    VIDEO_WIDTH, VIDEO_HEIGHT,
    IMAGE_SAMPLER_STEPS, IMAGE_SAMPLER_NAME, IMAGE_SAMPLER_CFG,
    COMFYUI_BATCH_SUBMIT, COMFYUI_POLL_WORKERS,
    FLUX_UNET, FLUX_CLIP_T5, FLUX_CLIP_L, FLUX_VAE, FLUX_GUIDANCE,
)
from modules.logger import get_logger

log = get_logger("image_generator")

NEGATIVE_PROMPT = (
    "text, watermark, logo, blurry, low quality, deformed, ugly, "
    "duplicate, extra limbs, bad anatomy, nsfw, violence, gore, "
    "cartoon, anime, illustration"   # keep horror realistic
)

# ─── Cerebras Prompt for Image Prompt Generation ──────────────────────────────

CEREBRAS_SCENE_PROMPT = """You are an expert at writing Stable Diffusion / ComfyUI image generation prompts for YouTube Shorts.

CHANNEL: {channel_name}
AUDIENCE: {audience}
VISUAL STYLE: {style}
NEGATIVE (never include): text, watermark, logo, face close-ups, people's identifiable faces

SCRIPT:
\"\"\"{script}\"\"\"

Task: Write exactly {n} ComfyUI image generation prompts that visually illustrate the {n} key narrative moments of this script IN ORDER. 

Rules for each prompt:
- 60–100 words maximum per prompt
- Highly specific to THIS script (use actual locations, settings, time period, mood from the script)
- Vertical 9:16 composition suitable for smartphone screens
- Include cinematic quality descriptors: "masterpiece, 4K, cinematic photography, professional quality"
- Match the visual style: {style}
- Each scene must be visually distinct from the others
- Safe for all audiences — no gore, no explicit violence, no identifiable real people

Return ONLY a valid JSON array of exactly {n} strings. No explanation, no markdown, just the JSON array:
["prompt 1 here", "prompt 2 here", ..., "prompt {n} here"]"""

CEREBRAS_THUMBNAIL_PROMPT = """You are an expert at writing Stable Diffusion / ComfyUI image prompts for YouTube Shorts thumbnails.

CHANNEL: {channel_name}
SCRIPT SUMMARY: {script_summary}
VISUAL STYLE: {style}

Write ONE eye-catching YouTube thumbnail image prompt for this video.
Rules:
- Must be extremely click-worthy and visually arresting
- No text or words in the image
- Vertical 9:16 format for Shorts
- 60–80 words max
- Include "professional YouTube thumbnail quality, highly detailed, 4K"
- Match the style: {style}

Return ONLY the prompt string. No explanation, no JSON, just the prompt text."""

# ─── Fallback Template Prompts ────────────────────────────────────────────────

FALLBACK_TEMPLATES = {
    "horror_crime": [
        "Dark foggy American suburb at night, {location}, empty street with flickering orange streetlights, "
        "dead leaves, chain-link fence, thick rolling fog, ominous atmosphere, horror movie establishing shot, "
        "no people visible, cinematic 4K photography, anamorphic lens flare, masterpiece",

        "US police crime scene with yellow tape, {location}, forensic investigators in white gear, "
        "evidence markers on wet asphalt, red and blue police light reflections, "
        "professional crime scene photography, {year}, dramatic night photography, documentary style",

        "Isolated American parking lot at night, {location}, single broken streetlight, "
        "abandoned car, grainy CCTV camera aesthetic, security footage look, "
        "long shadows stretching across empty asphalt, noir photography, ominous quiet",

        "US detective office, {location} Police Department, large cork evidence board with red string "
        "connecting photographs and newspaper clippings, manila folders, {year} cold case, "
        "overhead fluorescent lighting, realistic documentary photography",

        "Vintage newspaper front page, {location} Gazette, bold black headline, {year}, "
        "grainy black and white press photograph, worn yellowed paper texture, "
        "dramatic journalism aesthetic, authentic 1980s-2000s print media",

        "Creepy abandoned house interior, {location}, {year}, dusty furniture, single lamp casting "
        "long shadows, cracked mirror, old calendar on wall, horror atmosphere, "
        "documentary photography style, film grain, unsettling quiet",

        "FBI field office {location}, {year}, agents reviewing case files at conference table, "
        "American flag visible, serious federal investigation atmosphere, documentary photography",

        "American courthouse exterior, {location}, {year}, wide stone steps, American flag flying, "
        "dramatic stormy sky, justice and law theme, cinematic quality, desaturated color grade",
    ],
    "manners_fun": [
        "Cartoon American classroom scene, kids acting out a manners problem, bright Pixar style, "
        "diverse US children, expressive funny faces, warm classroom, educational illustration",

        "Cute cartoon American child character with big expressive eyes, bright colorful room, "
        "friendly and approachable, Pixar animation quality, warm home setting, cheerful sunlit atmosphere",

        "Friendly cartoon teacher explaining {lesson} to diverse US kids, bright classroom, "
        "colorful educational posters, American school setting, Pixar quality, engaged happy students",

        "Cartoon kids practicing {lesson} together, American school playground, bright sunny day, "
        "huge smiles, thumbs up, colorful clothing, Pixar style, encouraging positive atmosphere",

        "Cartoon child receiving gold star sticker for good manners, elementary school classroom, "
        "celebration confetti, beaming faces, Pixar quality digital art, warm golden light",

        "Cartoon diverse US kids sharing and being kind at recess, American playground, "
        "bright sunshine, colorful equipment, friendship theme, Pixar animation style",

        "Cartoon child having a-ha moment about {lesson}, lightbulb above head, "
        "American home or school, bright warm colors, Pixar quality, understanding expression",

        "Celebration scene with cartoon diverse American kids showing perfect manners, "
        "colorful banner, confetti, stars, hearts, Pixar animation quality, golden hour lighting",
    ],
    "cartoon_stories": [
        "Cute cartoon character {character} in dramatic action pose, bright bold comic book colors, "
        "American cartoon style, huge expressive eyes, energy lines, Cartoon Network quality",

        "Cartoon character {character} in colorful American hometown, bright saturated colors, "
        "fun cartoon buildings, sunny day, Cartoon Network animation style, welcoming world",

        "Cartoon character {character} face-to-face with silly problem, shocked expression, "
        "American cartoon style, bright colors with dark storm cloud, Cartoon Network quality",

        "Cartoon character {character} hilariously failing to solve the problem, "
        "slapstick style, stars and swirls, bright colors, Cartoon Network quality",

        "Wise funny cartoon mentor appearing to help {character}, magical sparkle effect, "
        "American cartoon style, warm golden light, Cartoon Network quality",

        "Cartoon character {character} having breakthrough realization, lightbulb over head, "
        "glowing eyes of understanding, bright warm colors, Cartoon Network quality",

        "Cartoon character {character} triumphantly solving the problem, victory pose, "
        "confetti, stars, Cartoon Network animation style, bright saturated colors",

        "Cartoon scene with {character} and friends holding lesson banner, "
        "bright celebration colors, hearts and stars, Cartoon Network quality, friendship theme",
    ],
}

FALLBACK_THUMBNAIL = {
    "horror_crime": (
        "YouTube Shorts thumbnail, {location} true crime, dark ominous background, "
        "dramatic red lighting, {year}, high contrast cinematic photography, empty street at night, "
        "professional YouTube thumbnail quality, compelling composition, no text"
    ),
    "manners_fun": (
        "YouTube Shorts kids thumbnail, bright yellow gradient background, "
        "Pixar-style cartoon children with huge excited expressions, colorful stars and hearts, "
        "educational vibe, maximum visual appeal, professional thumbnail, no text"
    ),
    "cartoon_stories": (
        "YouTube Shorts cartoon thumbnail, {character} in exciting action pose, "
        "bright vibrant rainbow colors, Cartoon Network style, huge expressive face, "
        "dynamic composition, premium cartoon art, professional thumbnail, no text"
    ),
}


class ImageGenerator:
    """Generates 8 scene images + thumbnail per short via Cerebras prompts → ComfyUI."""

    def __init__(self, channel: str = None, comfyui_url: str = None):
        # Use per-channel URL if set (3-GPU mode), else shared URL
        if comfyui_url:
            self.url = comfyui_url.rstrip("/")
        elif channel and channel in COMFYUI_URLS:
            self.url = COMFYUI_URLS[channel].rstrip("/")
        else:
            self.url = COMFYUI_URL.rstrip("/")
        # Cerebras client
        try:
            from cerebras.cloud.sdk import Cerebras
            self._cerebras = Cerebras(api_key=CEREBRAS_API_KEY)
        except Exception:
            self._cerebras = None

    # ─── Public API ───────────────────────────────────────────────────────────

    def generate_scenes(self, channel: str, script: str,
                         output_dir: Path, num_scenes: int = 8, idea: dict = None) -> list[Path]:
        """
        Fast path: submit ALL jobs to ComfyUI queue simultaneously,
        then poll all concurrently.  GPU never sits idle between submissions.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        prompts = self._cerebras_scene_prompts(channel, script, num_scenes)
        if prompts:
            log.info(f"[{channel}] Cerebras wrote {len(prompts)} custom prompts")
        else:
            prompts = self._fallback_prompts(channel, script, num_scenes, idea)
            log.info(f"[{channel}] Using fallback template prompts")

            log.info(f"  Prompt: {prompt[:80]}...")
            time.sleep(0.5)

        return paths

    def generate_thumbnail(self, channel: str, output_dir: Path,
                            script: str = "", idea: dict = None) -> Path:
        """Generate raw thumbnail image (text overlay added by thumbnail_generator)."""
        output_dir = Path(output_dir)
        out_path   = output_dir / "thumbnail_raw.png"

        prompt = self._cerebras_thumbnail_prompt(channel, script)
        if not prompt:
            ctx    = self._extract_context(script, idea)
            prompt = self._fill(FALLBACK_THUMBNAIL[channel], ctx)

        self._generate_image(prompt, out_path)
        log.info(f"[{channel}] Thumbnail: {out_path.name}")
        return out_path

    # ─── Batch / Concurrent Submission ──────────────────────────────────────────

    def _batch_generate(self, jobs: list[tuple], channel: str) -> list[Path]:
        """
        Submit ALL jobs to ComfyUI queue immediately, then poll concurrently.
        ComfyUI processes jobs sequentially on GPU but we waste zero time
        between submissions and poll all futures in parallel.
        """
        # Step 1 — Submit all N workflows at once
        prompt_ids = {}   # prompt_id -> output_path
        for prompt_text, out_path in jobs:
            try:
                workflow = self._build_workflow(prompt_text, VIDEO_WIDTH, VIDEO_HEIGHT)
                r = requests.post(f"{self.url}/prompt",
                                   json={"prompt": workflow}, timeout=15)
                r.raise_for_status()
                pid = r.json()["prompt_id"]
                prompt_ids[pid] = out_path
                log.info(f"[{channel}] Queued {out_path.name} → id={pid[:8]}")
            except Exception as e:
                log.error(f"[{channel}] Submit failed for {out_path.name}: {e}")

        if not prompt_ids:
            return [p for _, p in jobs]

        log.info(
            f"[{channel}] {len(prompt_ids)}/{len(jobs)} jobs queued — "
            f"polling with {COMFYUI_POLL_WORKERS} workers..."
        )

        # Step 2 — Poll all jobs concurrently
        def poll_one(pid_path):
            pid, out_path = pid_path
            for _ in range(720):   # max 12 minutes per image
                time.sleep(1)
                try:
                    history = requests.get(
                        f"{self.url}/history/{pid}", timeout=10
                    ).json()
                    if pid in history:
                        outputs = history[pid].get("outputs", {})
                        for node_out in outputs.values():
                            if "images" in node_out:
                                info = node_out["images"][0]
                                img = requests.get(
                                    f"{self.url}/view",
                                    params={
                                        "filename": info["filename"],
                                        "subfolder": info.get("subfolder", ""),
                                        "type": info.get("type", "output"),
                                    },
                                    timeout=30,
                                ).content
                                out_path.write_bytes(img)
                                log.info(f"[{channel}] Done: {out_path.name}")
                                return out_path
                        break
                except Exception:
                    pass
            log.warning(f"[{channel}] Timeout polling {out_path.name}")
            return out_path

        with ThreadPoolExecutor(max_workers=COMFYUI_POLL_WORKERS) as ex:
            futures = {ex.submit(poll_one, item): item for item in prompt_ids.items()}
            results = []
            for fut in as_completed(futures):
                results.append(fut.result())

        return sorted(results)

    # ─── Cerebras: Scene Prompt Generation ───────────────────────────────────

    def _cerebras_scene_prompts(self, channel: str, script: str, num_scenes: int = 8) -> list[str] | None:
        """
        Ask Cerebras to write N custom ComfyUI image prompts from the script.
        Returns list[str] of length num_scenes, or None on failure.
        """
        if not self._cerebras or not script:
            return None
        if "YOUR_" in CEREBRAS_API_KEY:
            return None

        cfg = CHANNELS[channel]
        style_desc = {
            "horror_crime":    "Dark, realistic, cinematic horror-documentary photography, desaturated colors",
            "manners_fun":     "Bright, cheerful, Pixar-quality 3D animated cartoon illustration",
            "cartoon_stories": "Bold, colorful, energetic Cartoon Network / comic book style animation",
        }[channel]

        prompt_text = CEREBRAS_SCENE_PROMPT.format(
            channel_name = cfg["name"],
            audience     = cfg["audience"],
            style        = style_desc,
            script       = script[:900],   # trim to stay within context limit
            n            = num_scenes,
        )

        try:
            response = self._cerebras.chat.completions.create(
                model      = CEREBRAS_MODEL,               # cbsgpt-120b
                messages   = [{"role": "user", "content": prompt_text}],
                max_tokens = CEREBRAS_MAX_TOKENS_PROMPTS,  # 1400
                temperature= CEREBRAS_TEMP_STRUCTURED,     # 0.30 — clean JSON array
            )
            raw = response.choices[0].message.content.strip()

            # Extract JSON array from response (handle markdown code blocks)
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
            prompts = json.loads(raw)

            if (
                isinstance(prompts, list)
                and len(prompts) >= num_scenes
                and all(isinstance(p, str) and len(p) > 10 for p in prompts)
            ):
                log.info(f"[{channel}] Cerebras wrote {len(prompts)} custom scene prompts")
                return prompts[:num_scenes]
            else:
                log.warning(f"[{channel}] Cerebras prompt list invalid, using fallback")
                return None

        except json.JSONDecodeError as e:
            log.warning(f"[{channel}] Cerebras JSON parse failed: {e}")
            return None
        except Exception as e:
            log.warning(f"[{channel}] Cerebras scene prompt call failed: {e}")
            return None

    # ─── Cerebras: Thumbnail Prompt Generation ────────────────────────────────

    def _cerebras_thumbnail_prompt(self, channel: str, script: str) -> str | None:
        """Ask Cerebras for a single custom thumbnail prompt."""
        if not self._cerebras or not script:
            return None
        if "YOUR_" in CEREBRAS_API_KEY:
            return None

        cfg = CHANNELS[channel]
        style_desc = {
            "horror_crime":    "Dark, ominous, dramatic true crime photography",
            "manners_fun":     "Bright, cheerful, Pixar cartoon illustration",
            "cartoon_stories": "Bold, colorful Cartoon Network animation style",
        }[channel]

        prompt_text = CEREBRAS_THUMBNAIL_PROMPT.format(
            channel_name   = cfg["name"],
            script_summary = script[:300],
            style          = style_desc,
        )

        try:
            response = self._cerebras.chat.completions.create(
                model      = CEREBRAS_MODEL,               # cbsgpt-120b
                messages   = [{"role": "user", "content": prompt_text}],
                max_tokens = 200,
                temperature= CEREBRAS_TEMP_STRUCTURED,     # 0.30
            )
            prompt = response.choices[0].message.content.strip().strip('"')
            if len(prompt) > 20:
                log.info(f"[{channel}] Cerebras thumbnail prompt: {prompt[:70]}...")
                return prompt
        except Exception as e:
            log.warning(f"[{channel}] Cerebras thumbnail prompt failed: {e}")

        return None

    # ─── Fallback Template Prompts ────────────────────────────────────────────

    def _fallback_prompts(self, channel: str, script: str,
                           num_scenes: int = 8, idea: dict = None) -> list[str]:
        """Generate prompts from templates + context extraction."""
        ctx       = self._extract_context(script, idea)
        templates = FALLBACK_TEMPLATES[channel]
        # Duplicate templates if we need more scenes than we have templates
        while len(templates) < num_scenes:
            templates += FALLBACK_TEMPLATES[channel]
        return [self._fill(t, ctx) for t in templates[:num_scenes]]

    # ─── Context Extraction ───────────────────────────────────────────────────

    @staticmethod
    def _extract_context(script: str, idea: dict = None) -> dict:
        ctx = {
            "location":  "a quiet American town",
            "year":      "in recent years",
            "character": "our hero",
            "lesson":    "being kind and respectful",
        }
        if not script:
            return ctx

        year_m = re.search(r'\b(19[4-9]\d|20[0-2]\d)\b', script)
        if year_m:
            ctx["year"] = year_m.group(0)

        us_places = [
            "Alabama","Alaska","Arizona","Arkansas","California","Colorado",
            "Connecticut","Delaware","Florida","Georgia","Hawaii","Idaho",
            "Illinois","Indiana","Iowa","Kansas","Kentucky","Louisiana",
            "Maine","Maryland","Massachusetts","Michigan","Minnesota",
            "Mississippi","Missouri","Montana","Nebraska","Nevada",
            "New Hampshire","New Jersey","New Mexico","New York",
            "North Carolina","North Dakota","Ohio","Oklahoma","Oregon",
            "Pennsylvania","Rhode Island","South Carolina","South Dakota",
            "Tennessee","Texas","Utah","Vermont","Virginia",
            "Washington","West Virginia","Wisconsin","Wyoming",
            "Chicago","Los Angeles","Houston","Phoenix","Philadelphia",
            "San Antonio","San Diego","Dallas","Jacksonville","Austin",
            "Detroit","Memphis","Seattle","Denver","Boston","Atlanta",
        ]
        for p in us_places:
            if p.lower() in script.lower():
                ctx["location"] = p
                break

        name_m = re.search(r'\bnamed\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', script)
        if name_m:
            ctx["character"] = name_m.group(1)

        if idea:
            ctx["lesson"]    = idea.get("lesson", ctx["lesson"])
            ctx["character"] = idea.get("character_name", ctx["character"])

        return ctx

    # ─── ComfyUI Core ─────────────────────────────────────────────────────────

    def _generate_image(self, prompt: str, output_path: Path,
                         width: int = VIDEO_WIDTH,
                         height: int = VIDEO_HEIGHT) -> bool:
        """Submit a prompt to ComfyUI, poll until done, download and save."""
        try:
            workflow = self._build_workflow(prompt, width, height)
            r = requests.post(f"{self.url}/prompt",
                               json={"prompt": workflow}, timeout=30)
            r.raise_for_status()
            prompt_id = r.json()["prompt_id"]

            for _ in range(600):        # max 10 minutes per image
                time.sleep(1)
                history = requests.get(
                    f"{self.url}/history/{prompt_id}", timeout=10
                ).json()
                if prompt_id in history:
                    outputs = history[prompt_id].get("outputs", {})
                    for node_out in outputs.values():
                        if "images" in node_out:
                            info = node_out["images"][0]
                            img_bytes = requests.get(
                                f"{self.url}/view",
                                params={
                                    "filename": info["filename"],
                                    "subfolder": info.get("subfolder", ""),
                                    "type": info.get("type", "output"),
                                },
                                timeout=30,
                            ).content
                            output_path.write_bytes(img_bytes)
                            return True
                    break

        except Exception as e:
            log.error(f"ComfyUI image gen failed for {output_path.name}: {e}")

        return False

    @staticmethod
    def _fill(template: str, ctx: dict) -> str:
        """Safely fill template, leaving unknown keys unchanged."""
        try:
            return template.format(**ctx)
        except KeyError:
            return template

    @staticmethod
    def _build_workflow(prompt: str, width: int, height: int) -> dict:
        """
        Auto-selects FLUX.1-schnell (4 steps, fast, top quality).
        """
        return ImageGenerator._build_flux_workflow(prompt, width, height)

    @staticmethod
    def _build_flux_workflow(prompt: str, width: int, height: int) -> dict:
        """
        FLUX.1-schnell ComfyUI workflow.
        4 steps → ~20s per 1080×1920 image on RTX 3090.

        Required model files in ComfyUI/models/:
          unet/  → flux1-schnell.safetensors
          clip/  → t5xxl_fp8_e4m3fn.safetensors + clip_l.safetensors
          vae/   → ae.safetensors
        """
        import uuid as _uuid
        seed = int(_uuid.uuid4().int % 2**32)
        return {
            # Load FLUX UNET (Diffusion Transformer)
            "1": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name":    FLUX_UNET,
                    "weight_dtype": "fp8_e4m3fn",  # saves VRAM, no quality loss
                },
            },
            # Load dual text encoders (T5-XXL + CLIP-L)
            "2": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": FLUX_CLIP_T5,
                    "clip_name2": FLUX_CLIP_L,
                    "type":       "flux",
                },
            },
            # Load FLUX VAE
            "3": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": FLUX_VAE},
            },
            # Encode prompt (FLUX uses single positive, no negative)
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["2", 0]},
            },
            # FluxGuidance (replaces CFG — guidance=3.5 for cinematic quality)
            "5": {
                "class_type": "FluxGuidance",
                "inputs": {
                    "conditioning": ["4", 0],
                    "guidance":     FLUX_GUIDANCE,  # 3.5
                },
            },
            # ModelSamplingFlux (necessary for correct noise scaling)
            "6": {
                "class_type": "ModelSamplingFlux",
                "inputs": {
                    "model":      ["1", 0],
                    "max_shift":  1.15,
                    "base_shift": 0.5,
                    "width":      width,
                    "height":     height,
                },
            },
            # Empty latent at target resolution
            "7": {
                "class_type": "EmptySD3LatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            # KSampler — euler + 4 steps (FLUX.1-schnell is distilled)
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "model":        ["6", 0],
                    "positive":     ["5", 0],
                    "negative":     ["4", 0],  # FLUX ignores negative; pass same cond
                    "latent_image": ["7", 0],
                    "seed":         seed,
                    "steps":        IMAGE_SAMPLER_STEPS,  # 4
                    "cfg":          IMAGE_SAMPLER_CFG,    # 1.0 (FLUX uses guidance node)
                    "sampler_name": IMAGE_SAMPLER_NAME,   # "euler"
                    "scheduler":    "simple",
                    "denoise":      1.0,
                },
            },
            # Decode
            "9": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["8", 0], "vae": ["3", 0]},
            },
            # Save
            "10": {
                "class_type": "SaveImage",
                "inputs": {"images": ["9", 0], "filename_prefix": "flux_scene"},
            },
        }

