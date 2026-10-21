# Quick Math

One small operation on one or two numbers, in a node three rows tall. For the many one-step sums a graph needs without a full math expression node.

## Inputs
- **operation**: what to do.
- **a**: an int or a float.
- **b** *(optional)*: an int or a float. One-number operations ignore it.

## Outputs
- **int**: the result as an int, cut toward zero (3.5 → 3, −3.5 → −3), as core's math node does.
- **float**: the result as a float.

## Operations

| Two numbers | | One number | |
| --- | --- | --- | --- |
| add | a + b | increment | a + 1 |
| subtract | a − b | decrement | a − 1 |
| multiply | a × b | floor | rounds down |
| divide | a ÷ b | ceil | rounds up |
| modulo | remainder of a ÷ b | round | nearest, halves away from zero |
| complement | what to add to a to reach the next multiple of b | absolute | drops the sign |
| | | negate | flips the sign |

**complement** is modulo's other half: 23 modulo 7 is **2**, 23 complement 7 is **5** (23 + 5 = 28). An **a** that's already a multiple gives **0**, not **b**: 21 complement 7 is 0, since nothing needs adding. Handy for padding a count up to a multiple.

**modulo** follows **b**'s sign, as Python's `%` does: −7 modulo 3 is 2.

**round** sends halves away from zero: 2.5 → 3, −2.5 → −3. (Python's own `round` sends them to the even neighbour, 2.5 → 2.)

## Errors
- Dividing by zero, in divide, modulo or complement.
- A two-number operation with **b** unconnected.
