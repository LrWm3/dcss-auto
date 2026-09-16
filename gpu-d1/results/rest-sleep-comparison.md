# Visible sleep-status rerun: results

Fresh seed-0 wait-only and rest-enabled models, 10M decisions each. All settings match the previous rest experiment except 40 visible-enemy sleep-status inputs. New input weights start at zero; original initial weights are preserved. One training seed per arm; this is an exploratory comparison, not a multi-seed significance test.

## Ordinary held-out floors

| Model | Sleep input | Clear | Death | Timeout | Training seconds |
|---|---|---:|---:|---:|---:|
| wait | False | 81.2% | 17.6% | 1.3% | 208.8 |
| rest | False | 80.8% | 18.4% | 0.9% | 220.2 |
| wait | True | 80.4% | 18.5% | 1.2% | 213.3 |
| rest | True | 84.7% | 14.5% | 0.9% | 224.3 |

## Recovery probes: sampled

Each cell has 128 combat seeds × eight orientations. Combat seeds repeat across orientations. Sleep is visible only inside LOS. Rest remains masked by any visible enemy. Percentages below describe policy behavior and survival, not training-seed uncertainty.

| Position | HP | Enemy | Model | Sleep input | Clear | Waited while asleep | Rested before wake | Mean HP at wake |
|---|---:|---|---|---|---:|---:|---:|---:|
| off_axis_wake_plus_one | 2 | reference | wait | False | 88.7% | 0.0% | 0.0% | 2.44 |
| off_axis_wake_plus_one | 2 | hard | wait | False | 36.8% | 0.0% | 0.0% | 2.12 |
| off_axis_wake_plus_one | 9 | reference | wait | False | 98.9% | 0.0% | 0.0% | 9.41 |
| off_axis_wake_plus_one | 9 | hard | wait | False | 81.1% | 0.0% | 0.0% | 9.08 |
| off_axis_wake_plus_one | 18 | reference | wait | False | 99.3% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 18 | hard | wait | False | 91.9% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 2 | reference | wait | False | 88.5% | 0.0% | 0.0% | 2.57 |
| straight_vision_edge | 2 | hard | wait | False | 41.4% | 0.0% | 0.0% | 2.26 |
| straight_vision_edge | 9 | reference | wait | False | 98.9% | 0.0% | 0.0% | 9.61 |
| straight_vision_edge | 9 | hard | wait | False | 83.5% | 0.0% | 0.0% | 9.20 |
| straight_vision_edge | 18 | reference | wait | False | 99.1% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 18 | hard | wait | False | 91.6% | 0.1% | 0.0% | 18.00 |
| outside_vision | 2 | reference | wait | False | 89.7% | 0.0% | 0.0% | 4.13 |
| outside_vision | 2 | hard | wait | False | 50.2% | 0.0% | 0.0% | 4.06 |
| outside_vision | 9 | reference | wait | False | 97.9% | 0.0% | 0.0% | 11.03 |
| outside_vision | 9 | hard | wait | False | 83.9% | 0.0% | 0.0% | 11.01 |
| outside_vision | 18 | reference | wait | False | 99.1% | 0.0% | 0.0% | 18.00 |
| outside_vision | 18 | hard | wait | False | 93.1% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 2 | reference | wait | True | 82.0% | 0.0% | 0.0% | 2.20 |
| off_axis_wake_plus_one | 2 | hard | wait | True | 31.8% | 0.0% | 0.0% | 2.04 |
| off_axis_wake_plus_one | 9 | reference | wait | True | 98.2% | 0.2% | 0.0% | 9.15 |
| off_axis_wake_plus_one | 9 | hard | wait | True | 76.0% | 0.0% | 0.0% | 9.01 |
| off_axis_wake_plus_one | 18 | reference | wait | True | 99.8% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 18 | hard | wait | True | 93.8% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 2 | reference | wait | True | 82.1% | 0.0% | 0.0% | 2.02 |
| straight_vision_edge | 2 | hard | wait | True | 36.8% | 0.0% | 0.0% | 2.00 |
| straight_vision_edge | 9 | reference | wait | True | 98.7% | 0.1% | 0.0% | 9.02 |
| straight_vision_edge | 9 | hard | wait | True | 79.6% | 0.0% | 0.0% | 9.00 |
| straight_vision_edge | 18 | reference | wait | True | 99.7% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 18 | hard | wait | True | 95.5% | 0.0% | 0.0% | 18.00 |
| outside_vision | 2 | reference | wait | True | 82.3% | 0.4% | 0.0% | 4.03 |
| outside_vision | 2 | hard | wait | True | 39.7% | 0.4% | 0.0% | 4.02 |
| outside_vision | 9 | reference | wait | True | 98.7% | 0.3% | 0.0% | 10.99 |
| outside_vision | 9 | hard | wait | True | 81.4% | 0.3% | 0.0% | 11.02 |
| outside_vision | 18 | reference | wait | True | 99.6% | 0.7% | 0.0% | 18.00 |
| outside_vision | 18 | hard | wait | True | 92.7% | 0.8% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 2 | reference | rest | False | 84.5% | 0.0% | 5.2% | 2.83 |
| off_axis_wake_plus_one | 2 | hard | rest | False | 27.2% | 0.0% | 0.9% | 2.14 |
| off_axis_wake_plus_one | 9 | reference | rest | False | 97.1% | 0.0% | 3.4% | 9.31 |
| off_axis_wake_plus_one | 9 | hard | rest | False | 67.4% | 0.0% | 0.3% | 9.03 |
| off_axis_wake_plus_one | 18 | reference | rest | False | 97.9% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 18 | hard | rest | False | 88.3% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 2 | reference | rest | False | 86.5% | 0.0% | 5.8% | 2.92 |
| straight_vision_edge | 2 | hard | rest | False | 26.9% | 0.0% | 1.0% | 2.16 |
| straight_vision_edge | 9 | reference | rest | False | 98.3% | 0.0% | 7.2% | 9.65 |
| straight_vision_edge | 9 | hard | rest | False | 69.1% | 0.0% | 0.3% | 9.03 |
| straight_vision_edge | 18 | reference | rest | False | 98.3% | 0.1% | 0.0% | 18.00 |
| straight_vision_edge | 18 | hard | rest | False | 88.1% | 0.0% | 0.0% | 18.00 |
| outside_vision | 2 | reference | rest | False | 93.5% | 0.0% | 70.9% | 13.34 |
| outside_vision | 2 | hard | rest | False | 68.3% | 0.0% | 70.0% | 13.20 |
| outside_vision | 9 | reference | rest | False | 99.2% | 0.0% | 92.3% | 17.31 |
| outside_vision | 9 | hard | rest | False | 83.1% | 0.0% | 93.6% | 17.42 |
| outside_vision | 18 | reference | rest | False | 98.5% | 0.0% | 0.0% | 18.00 |
| outside_vision | 18 | hard | rest | False | 85.9% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 2 | reference | rest | True | 77.2% | 0.0% | 6.2% | 2.98 |
| off_axis_wake_plus_one | 2 | hard | rest | True | 29.8% | 0.0% | 1.1% | 2.17 |
| off_axis_wake_plus_one | 9 | reference | rest | True | 98.3% | 0.1% | 3.7% | 9.33 |
| off_axis_wake_plus_one | 9 | hard | rest | True | 72.5% | 0.0% | 0.5% | 9.04 |
| off_axis_wake_plus_one | 18 | reference | rest | True | 99.7% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 18 | hard | rest | True | 90.8% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 2 | reference | rest | True | 80.1% | 0.0% | 5.3% | 2.84 |
| straight_vision_edge | 2 | hard | rest | True | 27.9% | 0.0% | 1.6% | 2.25 |
| straight_vision_edge | 9 | reference | rest | True | 98.3% | 0.0% | 4.5% | 9.40 |
| straight_vision_edge | 9 | hard | rest | True | 76.9% | 0.0% | 0.3% | 9.03 |
| straight_vision_edge | 18 | reference | rest | True | 99.4% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 18 | hard | rest | True | 91.8% | 0.0% | 0.0% | 18.00 |
| outside_vision | 2 | reference | rest | True | 96.7% | 0.3% | 90.6% | 16.50 |
| outside_vision | 2 | hard | rest | True | 86.2% | 0.1% | 92.5% | 16.80 |
| outside_vision | 9 | reference | rest | True | 99.7% | 0.0% | 98.6% | 17.88 |
| outside_vision | 9 | hard | rest | True | 90.2% | 0.0% | 98.6% | 17.88 |
| outside_vision | 18 | reference | rest | True | 99.4% | 0.1% | 0.0% | 18.00 |
| outside_vision | 18 | hard | rest | True | 91.9% | 0.2% | 0.0% | 18.00 |

## Recovery probes: greedy

Each cell has 128 combat seeds × eight orientations. Combat seeds repeat across orientations. Sleep is visible only inside LOS. Rest remains masked by any visible enemy. Percentages below describe policy behavior and survival, not training-seed uncertainty.

| Position | HP | Enemy | Model | Sleep input | Clear | Waited while asleep | Rested before wake | Mean HP at wake |
|---|---:|---|---|---|---:|---:|---:|---:|
| off_axis_wake_plus_one | 2 | reference | wait | False | 81.7% | 0.0% | 0.0% | 2.00 |
| off_axis_wake_plus_one | 2 | hard | wait | False | 39.1% | 0.0% | 0.0% | 2.00 |
| off_axis_wake_plus_one | 9 | reference | wait | False | 89.7% | 0.0% | 0.0% | 9.00 |
| off_axis_wake_plus_one | 9 | hard | wait | False | 77.9% | 0.0% | 0.0% | 9.00 |
| off_axis_wake_plus_one | 18 | reference | wait | False | 92.4% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 18 | hard | wait | False | 87.2% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 2 | reference | wait | False | 82.8% | 0.0% | 0.0% | 2.00 |
| straight_vision_edge | 2 | hard | wait | False | 35.5% | 0.0% | 0.0% | 2.00 |
| straight_vision_edge | 9 | reference | wait | False | 91.0% | 0.0% | 0.0% | 9.00 |
| straight_vision_edge | 9 | hard | wait | False | 75.4% | 0.0% | 0.0% | 9.00 |
| straight_vision_edge | 18 | reference | wait | False | 93.6% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 18 | hard | wait | False | 86.7% | 0.0% | 0.0% | 18.00 |
| outside_vision | 2 | reference | wait | False | 79.5% | 0.0% | 0.0% | 4.00 |
| outside_vision | 2 | hard | wait | False | 42.8% | 0.0% | 0.0% | 4.00 |
| outside_vision | 9 | reference | wait | False | 96.1% | 0.0% | 0.0% | 11.00 |
| outside_vision | 9 | hard | wait | False | 80.9% | 0.0% | 0.0% | 11.00 |
| outside_vision | 18 | reference | wait | False | 98.2% | 0.0% | 0.0% | 18.00 |
| outside_vision | 18 | hard | wait | False | 92.4% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 2 | reference | wait | True | 56.6% | 0.0% | 0.0% | 2.00 |
| off_axis_wake_plus_one | 2 | hard | wait | True | 26.7% | 0.0% | 0.0% | 2.00 |
| off_axis_wake_plus_one | 9 | reference | wait | True | 72.6% | 0.0% | 0.0% | 9.00 |
| off_axis_wake_plus_one | 9 | hard | wait | True | 70.1% | 0.0% | 0.0% | 9.00 |
| off_axis_wake_plus_one | 18 | reference | wait | True | 74.0% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 18 | hard | wait | True | 86.3% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 2 | reference | wait | True | 58.8% | 0.0% | 0.0% | 2.00 |
| straight_vision_edge | 2 | hard | wait | True | 28.7% | 0.0% | 0.0% | 2.00 |
| straight_vision_edge | 9 | reference | wait | True | 75.2% | 0.0% | 0.0% | 9.00 |
| straight_vision_edge | 9 | hard | wait | True | 70.9% | 0.0% | 0.0% | 9.00 |
| straight_vision_edge | 18 | reference | wait | True | 75.0% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 18 | hard | wait | True | 78.1% | 0.0% | 0.0% | 18.00 |
| outside_vision | 2 | reference | wait | True | 63.7% | 0.0% | 0.0% | 4.00 |
| outside_vision | 2 | hard | wait | True | 35.2% | 0.0% | 0.0% | 4.00 |
| outside_vision | 9 | reference | wait | True | 86.7% | 0.0% | 0.0% | 11.00 |
| outside_vision | 9 | hard | wait | True | 77.1% | 0.0% | 0.0% | 11.00 |
| outside_vision | 18 | reference | wait | True | 90.4% | 0.0% | 0.0% | 18.00 |
| outside_vision | 18 | hard | wait | True | 86.7% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 2 | reference | rest | False | 37.5% | 0.0% | 0.0% | 2.00 |
| off_axis_wake_plus_one | 2 | hard | rest | False | 9.9% | 0.0% | 0.0% | 2.00 |
| off_axis_wake_plus_one | 9 | reference | rest | False | 45.6% | 0.0% | 0.0% | 9.00 |
| off_axis_wake_plus_one | 9 | hard | rest | False | 30.9% | 0.0% | 0.0% | 9.00 |
| off_axis_wake_plus_one | 18 | reference | rest | False | 37.3% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 18 | hard | rest | False | 42.8% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 2 | reference | rest | False | 41.2% | 0.0% | 0.0% | 2.00 |
| straight_vision_edge | 2 | hard | rest | False | 12.5% | 0.0% | 0.0% | 2.00 |
| straight_vision_edge | 9 | reference | rest | False | 44.9% | 0.0% | 0.0% | 9.00 |
| straight_vision_edge | 9 | hard | rest | False | 30.5% | 0.0% | 0.0% | 9.00 |
| straight_vision_edge | 18 | reference | rest | False | 37.7% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 18 | hard | rest | False | 42.0% | 0.0% | 0.0% | 18.00 |
| outside_vision | 2 | reference | rest | False | 38.5% | 0.0% | 50.0% | 10.00 |
| outside_vision | 2 | hard | rest | False | 26.8% | 0.0% | 50.0% | 10.00 |
| outside_vision | 9 | reference | rest | False | 44.9% | 0.0% | 100.0% | 18.00 |
| outside_vision | 9 | hard | rest | False | 42.0% | 0.0% | 100.0% | 18.00 |
| outside_vision | 18 | reference | rest | False | 45.3% | 0.0% | 0.0% | 18.00 |
| outside_vision | 18 | hard | rest | False | 40.0% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 2 | reference | rest | True | 66.2% | 0.0% | 0.0% | 2.00 |
| off_axis_wake_plus_one | 2 | hard | rest | True | 28.2% | 0.0% | 0.0% | 2.00 |
| off_axis_wake_plus_one | 9 | reference | rest | True | 75.2% | 0.0% | 0.0% | 9.00 |
| off_axis_wake_plus_one | 9 | hard | rest | True | 64.1% | 0.0% | 0.0% | 9.00 |
| off_axis_wake_plus_one | 18 | reference | rest | True | 78.0% | 0.0% | 0.0% | 18.00 |
| off_axis_wake_plus_one | 18 | hard | rest | True | 75.0% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 2 | reference | rest | True | 67.8% | 0.0% | 0.0% | 2.00 |
| straight_vision_edge | 2 | hard | rest | True | 27.9% | 0.0% | 0.0% | 2.00 |
| straight_vision_edge | 9 | reference | rest | True | 76.6% | 0.0% | 0.0% | 9.00 |
| straight_vision_edge | 9 | hard | rest | True | 67.0% | 0.0% | 0.0% | 9.00 |
| straight_vision_edge | 18 | reference | rest | True | 74.2% | 0.0% | 0.0% | 18.00 |
| straight_vision_edge | 18 | hard | rest | True | 74.6% | 0.0% | 0.0% | 18.00 |
| outside_vision | 2 | reference | rest | True | 93.9% | 0.0% | 100.0% | 18.00 |
| outside_vision | 2 | hard | rest | True | 89.3% | 0.0% | 100.0% | 18.00 |
| outside_vision | 9 | reference | rest | True | 93.8% | 0.0% | 100.0% | 18.00 |
| outside_vision | 9 | hard | rest | True | 89.3% | 0.0% | 100.0% | 18.00 |
| outside_vision | 18 | reference | rest | True | 94.1% | 0.0% | 0.0% | 18.00 |
| outside_vision | 18 | hard | rest | True | 89.3% | 0.0% | 0.0% | 18.00 |
