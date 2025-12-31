#!/usr/bin/env python3
import sys

from common import safe_input
import opt1_duplicates_move
import opt2_rename_to_title
import opt3_flatten_to_root
import opt4_file_to_dir
import opt5_blinkist_prune_mp3


def main() -> int:
  print("")
  print("Audio Tool Menu")
  print("1) Find duplicates by Title and move one per title into an output directory")
  print("2) Rename files in place to Title metadata (Title.ext)")
  print("3) Flatten audio to a root directory (recursive move to root, add --dupN on conflicts, optional cleanup)")
  print("4) Move each audio file into a folder named after the file (current level only)")
  print("5) Blinkist: if m4a or m4b exists with same base name, delete mp3")
  print("q) Quit")
  print("")

  choice = safe_input("Choose an option: ")
  if choice is None:
    return 1
  choice = choice.strip().lower()

  if choice in {"q", "quit", "exit"}:
    return 0

  if choice == "1":
    return opt1_duplicates_move.run()

  if choice == "2":
    return opt2_rename_to_title.run()

  if choice == "3":
    return opt3_flatten_to_root.run()

  if choice == "4":
    return opt4_file_to_dir.run()

  if choice == "5":
    return opt5_blinkist_prune_mp3.run()

  print("Unknown option.")
  return 2


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except KeyboardInterrupt:
    sys.stderr.write("\nCancelled.\n")
    raise SystemExit(130)