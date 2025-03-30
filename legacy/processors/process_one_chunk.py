"""
Process a single chunk identified by find_unprocessed_chunks.py.
"""
import subprocess


def get_next_chunk_id():
    """Get the next unprocessed chunk ID."""
    try:
        result = subprocess.run(
            ["python", "find_unprocessed_chunks.py", "--limit", "1"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Extract the chunk ID from the output
        lines = result.stdout.strip().split('\n')
        for line in lines:
            try:
                # Try to convert each line to an integer to find the chunk ID
                chunk_id = int(line.strip())
                return chunk_id
            except ValueError:
                # Skip lines that are not integers
                pass
        
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error finding unprocessed chunks: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return None


def process_chunk(chunk_id):
    """Process a single chunk."""
    if chunk_id is None:
        print("No unprocessed chunk found.")
        return False
    
    print(f"Processing chunk {chunk_id}...")
    try:
        result = subprocess.run(
            ["python", "direct_process_chunk.py", str(chunk_id)],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"Successfully processed chunk {chunk_id}")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error processing chunk {chunk_id}: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False


def main():
    """Main function."""
    chunk_id = get_next_chunk_id()
    success = process_chunk(chunk_id)
    
    print("\nChecking progress...")
    try:
        subprocess.run(["python", "check_progress.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error checking progress: {e}")
    
    return success


if __name__ == "__main__":
    main()