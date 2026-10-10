#!/usr/bin/env bash
# Phase 0: fetch native ComfyUI 3D weights into the shared Desktop models tree.
# Resumable (curl -C -). Usage: bash scripts/fetch_models.sh
set -u
M=/c/Users/pete/Documents/ComfyUI/models
HF=https://huggingface.co/Comfy-Org
get() { # dir url
  mkdir -p "$M/$1"; f="$M/$1/$(basename "$2")"
  echo "START $1/$(basename "$2")"
  for try in 1 2 3; do
    curl -sfL -C - -o "$f.part" "$2" && mv "$f.part" "$f" && { echo "DONE $1/$(basename "$2") $(( $(stat -c %s "$f")/1048576 )) MB"; return; }
    [ -f "$f" ] && { echo "DONE $1/$(basename "$2") (exists)"; return; }
    sleep 5
  done
  echo "FAILED $1/$(basename "$2")"
}
get background_removal  $HF/BiRefNet/resolve/main/background_removal/birefnet.safetensors
get geometry_estimation $HF/MoGe/resolve/main/geometry_estimation/moge_2_vitl_normal_fp16.safetensors
get clip_vision         $HF/Pixal3D/resolve/main/clip_vision/dino_v3_L_naf_fp32.safetensors
get vae                 $HF/Pixal3D/resolve/main/vae/trellis_2_shape_vae_bf16.safetensors
get vae                 $HF/Pixal3D/resolve/main/vae/trellis_2_texture_vae_bf16.safetensors
get diffusion_models    $HF/TRELLIS.2/resolve/main/diffusion_models/trellis_2_int8_convrot.safetensors
get diffusion_models    $HF/Pixal3D/resolve/main/diffusion_models/pixal3d_multiview_int8_convrot.safetensors
get diffusion_models    $HF/Pixal3D/resolve/main/diffusion_models/pixal3d_int8_convrot.safetensors
get upscale_models      https://huggingface.co/Kim2091/UltraSharpV2/resolve/main/4x-UltraSharpV2.safetensors
get checkpoints         $HF/hunyuan3D_2.0_repackaged/resolve/main/split_files/hunyuan3d-dit-v2-mv_fp16.safetensors
echo ALL_FINISHED
