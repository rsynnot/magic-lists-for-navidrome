#!/usr/bin/env python3
"""
Script to wipe all playlist objects from the local database
"""

import sqlite3
import os

def wipe_all_playlists():
    """Wipe all playlist records from the database"""
    # Default database path from the DatabaseManager
    db_path = "magiclists.db"
    
    # Check if the database file exists
    if not os.path.exists(db_path):
        print(f"Database file {db_path} does not exist in the current directory.")
        print(f"Current working directory: {os.getcwd()}")
        
        # Check for the database in the backend directory (where the app runs from)
        backend_db_path = os.path.join("backend", "magiclists.db")
        if os.path.exists(backend_db_path):
            db_path = backend_db_path
            print(f"Found database in backend directory: {backend_db_path}")
        else:
            print("Database file not found in either location.")
            return False
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get count of existing playlists before deletion
        cursor.execute("SELECT COUNT(*) FROM playlists")
        playlist_count = cursor.fetchone()[0]
        print(f"Found {playlist_count} playlist(s) in the database")
        
        if playlist_count == 0:
            print("No playlists to delete.")
            return True
        
        # Get all playlist names before deletion (for information)
        cursor.execute("SELECT id, playlist_name FROM playlists")
        playlists = cursor.fetchall()
        print("\nPlaylists to be deleted:")
        for playlist_id, name in playlists:
            print(f"  - ID {playlist_id}: {name}")
        
        # Auto-confirm deletion (since this script is specifically for wiping playlists)
        print("Auto-confirming deletion of all playlists...")
        
        # Delete all playlist records
        cursor.execute("DELETE FROM playlists")
        print(f"Deleted {cursor.rowcount} playlist(s) from 'playlists' table")
        
        # Also delete scheduled playlist records if any (these are related to the playlists)
        cursor.execute("SELECT COUNT(*) FROM scheduled_playlists")
        scheduled_count = cursor.fetchone()[0]
        
        if scheduled_count > 0:
            print(f"Found {scheduled_count} scheduled playlist(s) in the database")
            cursor.execute("DELETE FROM scheduled_playlists")
            print(f"Deleted {cursor.rowcount} scheduled playlist(s) from 'scheduled_playlists' table")
        
        # Commit the changes
        conn.commit()
        
        # Get final count to confirm deletion
        cursor.execute("SELECT COUNT(*) FROM playlists")
        final_count = cursor.fetchone()[0]
        print(f"Remaining playlists after deletion: {final_count}")
        
        conn.close()
        print("✅ Database cleanup completed successfully!")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("Wiping all playlist objects from the database...")
    success = wipe_all_playlists()
    
    if success:
        print("\n✅ All playlist objects have been successfully wiped!")
    else:
        print("\n❌ Failed to wipe playlist objects.")