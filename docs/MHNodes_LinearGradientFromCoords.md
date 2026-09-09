# Linear Gradient from Coords

Creates a black-to-white linear gradient image defined by two points.

## Inputs
- **frame_width** / **frame_height**: output image size.
- **x1**, **y1**: gradient start point (black).
- **x2**, **y2**: gradient end point (white).
- **multiplier**: scales the ramp before clamping. `1.0` spreads the gradient evenly between the two points; higher values compress it into a harder edge near the start point.

## Outputs
- **IMAGE**: an RGB gradient, `[1, H, W, 3]`.

## Notes
- Pixels before the start point clamp to black, pixels past the end point clamp to white.
- If the start and end points are identical the result is a flat black frame.
