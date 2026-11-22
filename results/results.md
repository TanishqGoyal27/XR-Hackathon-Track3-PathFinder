| Method | ATE RMSE [m] | Blind 5 s [m] | After dropouts [m] |
|---|---|---|---|
| Static point (no motion) | 1.08 | - | - |
| Naive double integration | 147.21 | 304.37 | 151.96 |
| + zero-phase high-pass | 0.99 | 3.69 | 0.66 |
| + cleaning + blind relax (ours) | 0.62 | 0.65 | 0.64 |

Per sequence (ours):

| Sequence | ATE [m] | Blind [m] | Static ref [m] |
|---|---|---|---|
| room1_A | 0.465 | 0.637 | 1.002 |
| room1_B | 0.480 | 0.649 | 1.002 |
| room2_A | 0.411 | 0.657 | 1.219 |
| room2_B | 0.393 | 0.666 | 1.219 |
| room3_A | 0.566 | 0.685 | 1.254 |
| room3_B | 0.611 | 0.724 | 1.254 |
| room4_A | 0.919 | 0.811 | 1.079 |
| room4_B | 0.927 | 0.738 | 1.079 |
| room5_A | 0.616 | 0.746 | 0.933 |
| room5_B | 0.591 | 0.739 | 0.933 |
| room6_A | 0.705 | 0.359 | 0.988 |
| room6_B | 0.736 | 0.409 | 0.988 |
