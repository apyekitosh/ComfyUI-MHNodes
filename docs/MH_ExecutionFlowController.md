# Execution Flow Controller

Passes both inputs straight through, unchanged. It exists to force the order nodes run in.

## Inputs
- **signal**: anything. Whatever produces it runs before this node does.
- **value**: anything. Passed on once **signal** is ready.

## Outputs
- **signal** / **value**: the inputs, untouched. Each output takes the type of what's connected to its input, so a passed-through IMAGE stays an IMAGE.

## How it orders things

A node only runs once all its inputs are ready. Route a **value** through here with **signal** connected to some other node, and everything downstream of **value** now waits for that other node too, even though nothing about the value changed.

## Notes
- Nothing is copied: the outputs are the same objects that came in.
- Both inputs must be connected.
