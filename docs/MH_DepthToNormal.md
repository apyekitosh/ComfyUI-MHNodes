# Depth to Normal

Converts a depth image into a screen-space RGB normal map using depth differences between neighboring pixels. Works on images and batches, including video frames, without a camera model or 3D projection.

## Inputs

- **depth**: a grayscale depth map connected as IMAGE. RGB channels are averaged; alpha is ignored. Single-channel images are accepted too. Use grayscale depth rather than a colorized depth visualization.
- **strength**: scales depth differences per pixel. Default **10**. Increase for stronger slopes; **0** produces a flat normal map. Strength depends on the input depth range and resolution; resizing a depth map can require adjusting it.
- **invert_depth**: reverses the depth direction. Off treats brighter values as raised; turn it on if your depth convention needs the opposite direction.
- **flip_y**: flips the normal map's green channel. Off uses **+Y up (OpenGL)**; on gives the opposite green convention commonly used by DirectX tools.

## Output

- **normal**: an RGB IMAGE with the same batch, width and height as the input. Components are encoded from `[-1, 1]` into `[0, 1]`. Flat depth yields `(0.5, 0.5, 1.0)`.

Depth derivatives use central differences inside the image and one-sided differences at its boundaries. Normals are normalized to unit length before RGB encoding. The output is float32 on the input device; input samples are left unchanged.

This is a simple surface approximation: noise in depth becomes bumps, and sharp object boundaries become steep slopes. There is no depth normalization, smoothing, camera projection or recovery of detail missing from the input.

Uses only torch and ComfyUI APIs already present in the environment. No new dependencies.
