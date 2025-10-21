#!/usr/bin/env python3
"""
Test script to verify the new getSongsByGenre implementation
"""
import asyncio
import os
from dotenv import load_dotenv
from backend.navidrome_client import NavidromeClient

async def main():
    # Load environment variables
    load_dotenv()

    # Create Navidrome client
    client = NavidromeClient()

    try:
        # Test different genres
        genres_to_test = ["House", "Rock", "Electronic"]

        for genre in genres_to_test:
            print(f"\n🎵 Testing genre: {genre}")
            tracks = await client.get_tracks_by_genre(genre)
            print(f"✅ Found {len(tracks)} tracks")

            if len(tracks) > 0:
                # Show sample tracks
                sample = tracks[:3]
                for i, track in enumerate(sample, 1):
                    print(f"  {i}. {track['title']} - {track['artist']}")

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)