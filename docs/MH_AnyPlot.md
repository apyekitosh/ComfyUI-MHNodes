# Any Plot

Expands two lists into every combination, as the cells of a grid, so what follows runs once per cell.

## Inputs
- **list_1**: repeats as a whole: A B C A B C...
- **list_2**: repeats item by item: X X X Y Y Y...

## Outputs
- **list_1** / **list_2**: the expanded lists, the same length, paired cell by cell.
- **columns**: the length of list_1, the width of the grid.
- **rows**: the length of list_2, the height of the grid.

**columns** and **rows** are single values, not lists: the next node gets them once, not once per cell. That's what a node assembling the results into an image grid needs to know its shape.

## Example

`A B C` and `X Y Z` give

```
list_1:  A B C A B C A B C
list_2:  X X X Y Y Y Z Z Z
```

Read pair by pair, that's every combination, row after row: list_1 runs along each row, list_2 down the rows. Lists of different lengths work the same way: 2 × 4 gives 8 cells.

## Notes
- Each output takes the type of its input.
- The lists are taken whole rather than item by item, so feed it from *Any List* or any other list output.
- Either list empty is an error.
