"""
Simple script to process the next 10 chunks in sequence.
"""
import sys
import time
import subprocess
from typing import List


def find_next_chunk_ids(limit: int = 10) -> List[int]:
    """Find the next chunk IDs to process."""
    try:
        result = subprocess.run(
            ["python", "find_unprocessed_chunks.py", "--limit", str(limit)],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Extract the chunk IDs from the output
        lines = result.stdout.strip().split('\n')
        chunk_ids = []
        for line in lines:
            try:
                # Try to convert each line to an integer to find the chunk IDs
                chunk_id = int(line.strip())
                chunk_ids.append(chunk_id)
            except ValueError:
                # Skip lines that are not integers
                pass
        
        return chunk_ids
    except subprocess.CalledProcessError as e:
        print(f"Error finding unprocessed chunks: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return []


def process_chunks(chunk_ids: List[int]) -> int:
    """Process a list of chunks sequentially."""
    success_count = 0
    
    for i, chunk_id in enumerate(chunk_ids):
        print(f"Processing chunk {chunk_id} ({i+1}/{len(chunk_ids)})...")
        try:
            result = subprocess.run(
                ["python", "direct_process_chunk.py", str(chunk_id)],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"Successfully processed chunk {chunk_id}")
            success_count += 1
        except subprocess.CalledProcessError as e:
            print(f"Error processing chunk {chunk_id}: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
        
        # Small delay to avoid overloading the API or system
        time.sleep(1)
    
    return success_count


def check_progress():
    """Check and print the current progress."""
    try:
        subprocess.run(["python", "check_progress.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error checking progress: {e}")


def main():
    """Main function to process the next 10 chunks."""
    print("Finding next chunks to process...")
    chunk_ids = find_next_chunk_ids(10)
    
    if not chunk_ids:
        print("No unprocessed chunks found.")
        return
    
    print(f"Found {len(chunk_ids)} chunks to process: {chunk_ids}")
    
    print("Initial progress:")
    check_progress()
    
    print("\nProcessing chunks...")
    success_count = process_chunks(chunk_ids)
    
    print(f"\nProcessed {success_count}/{len(chunk_ids)} chunks successfully.")
    print("\nCurrent progress:")
    check_progress()


if __name__ == "__main__":
    main()