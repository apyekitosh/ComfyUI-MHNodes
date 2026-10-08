# Any to Pipe

Bundles up to 5 connections of any type into a single link, so a group of unrelated values can travel through a workflow — a switch, a reroute, a long jump across the canvas — as one wire instead of five.

## Inputs
- **1** – **5** *(all optional)*: anything at all. Model, image, string, latent, another pipe.

## Outputs
- **pipe**: the bundle, as a dedicated `MH_PIPE` type.

## Notes
- Empty slots stay empty. Leaving slot 2 unconnected does **not** shift slots 3–5 along; everything comes back out of the number it went in.
- The output is its own type, not a wildcard, so a pipe only fits a pipe input and a mis-drag is refused at the socket.

## Nesting

A pipe is an ordinary value, so one fits in a slot of another. That is how you get past 5:

```
Any to Pipe #1   inputs 1-5          -> pipe A
Any to Pipe #2   inputs 6-9 + pipe A -> pipe B
```

Unpacking pipe B gives 6, 7, 8, 9 and pipe A. Unpacking pipe A gives 1–5. There is no depth limit.

See [MH_PipeToAny.md](MH_PipeToAny.md) for the other half.
