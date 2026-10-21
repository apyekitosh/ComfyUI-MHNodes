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
| modulo | remainder, sign of **b** | round | nearest, halves away from zero |
| residual | remainder, sign of **a** | absolute | drops the sign |
| | | negate | flips the sign |

**modulo** and **residual** only differ for negative numbers: −7 modulo 3 is **2**, −7 residual 3 is **−1**. For positive numbers they're the same.

**round** sends halves away from zero: 2.5 → 3, −2.5 → −3. (Python's own `round` sends them to the even neighbour, 2.5 → 2.)

## Errors
- Dividing by zero, in divide, modulo or residual.
- A two-number operation with **b** unconnected.
