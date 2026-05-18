#!/usr/bin/env python3
import os
import sys
import tempfile
from pathlib import Path

DB_FILE = tempfile.NamedTemporaryFile(prefix="copilot-attachment-e2e-", suffix=".sqlite3", delete=False)
DB_FILE.close()
os.environ.setdefault("SQLITE_DB_PATH", DB_FILE.name)

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

import db
import time

def test_attachment_persistence():
    """Test that attachments persist through save and load cycle."""
    
    # Set up temp workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['WORKSPACE_DIR'] = tmpdir
        
        # Create a test conversation
        conversation = db.create_conversation("Attachment persistence")
        conv_id = conversation["id"]
        
        # Create test messages with attachments
        messages = [
            {
                "id": "msg1",
                "role": "user",
                "parts": [{"type": "text", "text": "Hello"}],
                "createdAt": int(time.time() * 1000),
                "parentId": None,
                "attachments": [
                    {
                        "id": "att1",
                        "name": "test.txt",
                        "path": f"attachments/{conv_id}/test.txt",
                        "contentType": "text/plain",
                        "type": "document"
                    }
                ]
            },
            {
                "id": "msg2",
                "role": "assistant",
                "parts": [{"type": "text", "text": "Hi there"}],
                "createdAt": int(time.time() * 1000),
                "parentId": "msg1",
                "attachments": None
            }
        ]
        
        # Save messages
        print("Saving messages with attachments...")
        db.replace_messages(conv_id, messages, "msg2")
        
        # Fetch messages back
        print("Fetching messages...")
        fetched = db.get_messages(conv_id)
        
        # Verify
        print(f"\nOriginal message 1 attachments: {messages[0].get('attachments')}")
        print(f"Fetched message 1 attachments: {fetched[0].get('attachments')}")
        
        # Check assertions
        assert len(fetched) == 2, f"Expected 2 messages, got {len(fetched)}"
        assert fetched[0]["id"] == "msg1", f"Expected msg1, got {fetched[0]['id']}"
        
        # The critical check: attachments should be preserved
        fetched_attachments = fetched[0].get("attachments")
        assert fetched_attachments is not None, "Attachments should not be None"
        assert len(fetched_attachments) == 1, f"Expected 1 attachment, got {len(fetched_attachments)}"
        assert fetched_attachments[0]["id"] == "att1", f"Expected att1, got {fetched_attachments[0]['id']}"
        assert fetched_attachments[0]["name"] == "test.txt", f"Expected test.txt, got {fetched_attachments[0]['name']}"
        
        print("\n✅ All assertions passed! Attachments persisted correctly.")

if __name__ == "__main__":
    try:
        test_attachment_persistence()
        print("\n✅ E2E attachment persistence test PASSED")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
