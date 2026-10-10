# Pad Frame Count (Advanced)

[Pad Frame Count](MH_PadFrameCount.md) with control over what the added frames contain. Every rule from that node applies unchanged.

## Extra inputs
- **pad_images_rule**: `Repeat` the edge frame, or `Solid Color`. Default `Solid Color`.
- **pad_masks_rule**: `Repeat` the edge mask, or `Solid Mask`. Default `Solid Mask`.
- **image_color**: colour for added image frames. Default `#808080`, neutral grey.
- **mask_value**: value for added mask frames, 0–1. Default `1`.

## Notes
- Set both rules to `Repeat` and the output is identical to the plain node — verified, not just intended.
- The colour accepts `#RRGGBB` or `#RRGGBBAA`. On a 4-channel image the alpha is used; on a 3-channel one it is ignored.
- Only the added frames are affected. Existing frames are never recoloured.
