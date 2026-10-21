"""Roll an inclusive integer range: dice [END] or dice START END."""
import argparse
import random

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("bounds", nargs="*", type=int, metavar="N")
args = parser.parse_args()
if len(args.bounds) > 2:
    parser.error("expected at most two bounds")
start, end = (1, 6) if not args.bounds else (1, args.bounds[0]) if len(args.bounds) == 1 else args.bounds
if start > end:
    parser.error("START must not exceed END")
print(random.randint(start, end))
