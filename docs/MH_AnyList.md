# Any List

Collects its inputs into a list. Whatever the list feeds runs **once per item**, which is how ComfyUI repeats part of a graph.

## Inputs
- **item0, item1, ...**: anything, all of one type. A new socket appears as the last one is connected, up to **100** (core's limit for growing inputs).

## Outputs
- **list**: the connected inputs, one item each, in socket order. It takes the type of what's connected, so a list of images stays a list of images.

## Notes
- Sockets left empty in the middle are skipped; the order of the rest is kept.
- Nothing connected at all is an error.
