import argparse
import json
import os
import sqlite3

from dotenv import load_dotenv
from Memories.Database import init_db
from StructuredOutput.Extractor import StructuredOutputError, extract_leave_request
from StructuredOutput.Store import save_leave_request

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Sensai structured leave request")
    parser.add_argument("text", help="Free-text leave request")
    parser.add_argument("--model", default=os.getenv("MODEL", "llama3"))
    parser.add_argument("--ollama-url",
                        default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    parser.add_argument("--save", metavar="USER_ID",
                        help="Save the request in the database for this existing user")
    args = parser.parse_args()

    try:
        data = extract_leave_request(args.text, args.ollama_url, args.model)
    except StructuredOutputError as e:
        print(f"Error: {e}")
        raise SystemExit(1)

    print(json.dumps(data, indent=2, ensure_ascii=False))

    if args.save:
        init_db()
        try:
            request_id = save_leave_request(args.save, data)
        except sqlite3.IntegrityError:
            print(f"Error: user '{args.save}' does not exist, request not saved.")
            raise SystemExit(1)
        print(f"Saved as leave request #{request_id} for {args.save}.")


if __name__ == "__main__":
    main()
