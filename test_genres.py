#!/usr/bin/env python3
"""
Test script to verify the get_genres implementation with getGenres endpoint
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
        print("🎵 Testing get_genres functionality...")

        # Test get_genres
        genres = await client.get_genres()
        print(f"✅ Found {len(genres)} genres")

        if len(genres) > 0:
            # Show first 10 genres
            print("📋 First 10 genres:")
            for i, genre in enumerate(genres[:10], 1):
                print(f"  {i}. {genre}")

            if len(genres) > 10:
                print(f"  ... and {len(genres) - 10} more")

        # Test with specific library if available
        library_id = os.getenv("NAVIDROME_LIBRARY_ID")
        if library_id:
            print(f"\n🎵 Testing get_genres with library ID: {library_id}")
            library_genres = await client.get_genres(library_id)
            print(f"✅ Found {len(library_genres)} genres in library")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)