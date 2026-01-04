#!/usr/bin/env python3
"""Check what tags exist in an MP3 file"""

import sys
from mutagen.id3 import ID3

# Ask user for file path
if len(sys.argv) > 1:
    path = sys.argv[1]
else:
    path = input("Enter MP3 file path: ")

print(f"Reading tags from: {path}\n")

try:
    audio = ID3(path)
    
    print("All tags in file:")
    print("="*60)
    for key, value in audio.items():
        print(f"{key}: {value}")
    
    print("\n" + "="*60)
    print("Specific tags we care about:")
    print("="*60)
    
    # Comment (COMM)
    comm_frames = [f for f in audio.values() if f.FrameID == 'COMM']
    if comm_frames:
        print(f"\nCOMM (Comment): {len(comm_frames)} frame(s)")
        for i, frame in enumerate(comm_frames):
            print(f"  Frame {i+1}: {frame.text}")
    else:
        print("\n❌ No COMM (Comment) tag")
    
    # Grouping (TIT1)
    if 'TIT1' in audio:
        print(f"\n✅ TIT1 (Grouping): {audio['TIT1'].text}")
    else:
        print("\n❌ No TIT1 (Grouping) tag")
    
    # Cover (APIC)
    apic_frames = [f for f in audio.values() if f.FrameID == 'APIC']
    if apic_frames:
        print(f"\n✅ APIC (Cover): {len(apic_frames)} image(s)")
    else:
        print("\n❌ No APIC (Cover) tag")
    
    # Genre (TCON)
    if 'TCON' in audio:
        print(f"\n✅ TCON (Genre): {audio['TCON'].text}")
    else:
        print("\n❌ No TCON (Genre) tag")

except Exception as e:
    print(f"Error: {e}")
