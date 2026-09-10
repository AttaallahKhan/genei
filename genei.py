import os
import sys
import json
import re
import requests

from tools.project_manager import current_project
from tools.memory_manager import load_history, add_history
from tools.file_manager import read_file, write_file, list_files, delete_file
from tools.command_runner import run_command
from tools.tool_manager import install_tool
from tools.github_manager import (
    list_repositories,
    get_repository,
    list_repo_files,
    get_repo_file,
    create_or_update_file,
    delete_github_file,
)


# ==================================================
# SETTINGS
# ==================================================

SETTINGS_FILE = os.path.expanduser("~/genei/config/settings.json")

with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)

DEFAULT_MODE = SETTINGS.get("default_model", "local")
MAX_TOKENS = SETTINGS.get("max_tokens", 800)

API_KEY = os.environ.get("OPENAI_API_KEY")

LOCAL_URL = "http://127.0.0.1:8080/v1/chat/completions"
LOCAL_MODEL = "qwen2.5-coder-0.5b-q4_k_m.gguf"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ONLINE_MODEL = "openai/gpt-5.2"


# ==================================================
# TOOLS
# ==================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a local text file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a local text file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List local files and folders.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a local file when explicitly requested.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a Termux command when explicitly requested. Never use for package installation.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "install_tool",
            "description": "Install a missing Termux package. User confirmation is required.",
            "parameters": {
                "type": "object",
                "properties": {"tool": {"type": "string"}},
                "required": ["tool"]
            }
        }
    },

    # ------------------------------------------------
    # GITHUB
    # ------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "list_github_repositories",
            "description": "List the authenticated user's GitHub repositories.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_github_repository",
            "description": "Get information about a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"}
                },
                "required": ["owner", "repo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_github_files",
            "description": "List files in a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "path": {"type": "string"}
                },
                "required": ["owner", "repo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_github_file",
            "description": "Read a file from a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "path": {"type": "string"}
                },
                "required": ["owner", "repo", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_github_file",
            "description": "Create or update a file in a GitHub repository and commit the change. ALWAYS call this tool for a GitHub file write. Do not ask for confirmation in your response.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "message": {"type": "string"},
                    "branch": {"type": "string"}
                },
                "required": [
                    "owner",
                    "repo",
                    "path",
                    "content",
                    "message"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_github_file",
            "description": "Delete a file from a GitHub repository and commit the deletion. ALWAYS call this tool for a GitHub file deletion. Do not ask for confirmation in your response.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "path": {"type": "string"},
                    "message": {"type": "string"},
                    "branch": {"type": "string"}
                },
                "required": [
                    "owner",
                    "repo",
                    "path",
                    "message"
                ]
            }
        }
    }
]


# ==================================================
# GITHUB WRITE CONFIRMATION
# ==================================================

def confirm_github_write(owner, repo, path, message):

    print()
    print("GitHub write requested:")
    print(f"Repository: {owner}/{repo}")
    print(f"File:       {path}")
    print(f"Commit:     {message}")

    answer = input("Proceed? [y/N]: ").strip().lower()

    return answer in ("y", "yes")


def confirm_github_delete(owner, repo, path, message):

    print()
    print("GitHub delete requested:")
    print(f"Repository: {owner}/{repo}")
    print(f"File:       {path}")
    print(f"Commit:     {message}")

    answer = input("Proceed? [y/N]: ").strip().lower()

    return answer in ("y", "yes")


# ==================================================
# TOOL EXECUTION
# ==================================================

def execute_tool(name, args):

    if name == "read_file":
        return read_file(args["path"])

    if name == "write_file":
        return write_file(args["path"], args["content"])

    if name == "list_files":
        return list_files(args["path"])

    if name == "delete_file":
        return delete_file(args["path"])

    if name == "run_command":
        return run_command(args["command"])

    if name == "install_tool":
        return install_tool(args["tool"])

    if name == "list_github_repositories":
        return list_repositories()

    if name == "get_github_repository":
        return get_repository(
            args["owner"],
            args["repo"]
        )

    if name == "list_github_files":
        return list_repo_files(
            args["owner"],
            args["repo"],
            args.get("path", "")
        )

    if name == "read_github_file":
        return get_repo_file(
            args["owner"],
            args["repo"],
            args["path"]
        )

    if name == "delete_github_file":

        owner = args["owner"]
        repo = args["repo"]
        path = args["path"]
        message = args["message"]
        branch = args.get("branch")

        if not confirm_github_delete(
            owner,
            repo,
            path,
            message
        ):
            return {
                "success": False,
                "cancelled": True,
                "message": "GitHub deletion cancelled by user."
            }

        try:

            result = delete_github_file(
                owner,
                repo,
                path,
                message,
                branch
            )

            return {
                "success": True,
                "message": "GitHub file deleted successfully.",
                "path": path,
                "commit": result["commit"]["message"],
                "sha": result["commit"]["sha"]
            }

        except Exception as e:

            return {
                "success": False,
                "message": f"GitHub delete failed: {e}"
            }


    if name == "write_github_file":

        owner = args["owner"]
        repo = args["repo"]
        path = args["path"]
        content = args["content"]
        message = args["message"]
        branch = args.get("branch")

        if not confirm_github_write(
            owner,
            repo,
            path,
            message
        ):
            return {
                "success": False,
                "cancelled": True,
                "message": "GitHub write cancelled by user."
            }

        try:

            result = create_or_update_file(
                owner,
                repo,
                path,
                content,
                message,
                branch
            )

            return {
                "success": True,
                "message": "GitHub file written successfully.",
                "path": result["content"]["path"],
                "commit": result["commit"]["message"],
                "sha": result["content"]["sha"]
            }

        except Exception as e:

            return {
                "success": False,
                "message": f"GitHub write failed: {e}"
            }

    return f"Unknown tool: {name}"


# ==================================================
# LOCAL REQUEST
# ==================================================

def local_request(messages):

    response = requests.post(
        LOCAL_URL,
        headers={
            "Content-Type": "application/json"
        },
        json={
            "model": LOCAL_MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": messages
        },
        timeout=120
    )

    if response.status_code != 200:
        print(f"Local Error {response.status_code}:")
        print(response.text)
        sys.exit(1)

    return response.json()["choices"][0]["message"]


# ==================================================
# ONLINE REQUEST
# ==================================================

def online_request(messages):

    if not API_KEY:
        print("Error: OPENAI_API_KEY is not set.")
        sys.exit(1)

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": ONLINE_MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto"
        },
        timeout=120
    )

    if response.status_code != 200:
        print(f"Online Error {response.status_code}:")
        print(response.text)
        sys.exit(1)

    return response.json()["choices"][0]["message"]


# ==================================================
# LOCAL DETERMINISTIC ROUTER
# ==================================================

def local_tool_request(prompt):

    text = prompt.strip()

    command_patterns = [
        r"^(?:run|execute)\s+(?:the\s+)?command\s+(?:exactly\s*:\s*)?(.+)$",
        r"^(?:run|execute)\s+(?:exactly\s*:\s*)?(.+)$",
        r"^use\s+(?:the\s+)?command\s+(?:exactly\s*:\s*)?(.+)$",
    ]

    for pattern in command_patterns:

        match = re.match(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            command = match.group(1).strip()

            if command:
                return {
                    "tool": "run_command",
                    "args": {
                        "command": command
                    }
                }

    match = re.match(
        r"^(?:list|show)\s+(?:the\s+)?files?(?:\s+in|\s+of)?\s+(.+)$",
        text,
        re.IGNORECASE
    )

    if match:
        return {
            "tool": "list_files",
            "args": {
                "path": match.group(1).strip()
            }
        }

    match = re.match(
        r"^(?:read|show\s+contents?\s+of|display)\s+(?:the\s+)?file\s+(.+)$",
        text,
        re.IGNORECASE
    )

    if match:
        return {
            "tool": "read_file",
            "args": {
                "path": match.group(1).strip()
            }
        }

    match = re.match(
        r"^(?:delete|remove)\s+(?:the\s+)?file\s+(.+)$",
        text,
        re.IGNORECASE
    )

    if match:
        return {
            "tool": "delete_file",
            "args": {
                "path": match.group(1).strip()
            }
        }

    match = re.match(
        r"^(?:install|add)\s+(?:the\s+)?(?:tool|package)\s+(.+)$",
        text,
        re.IGNORECASE
    )

    if match:
        return {
            "tool": "install_tool",
            "args": {
                "tool": match.group(1).strip()
            }
        }

    patterns = [
        r"^(?:create|make)\s+(?:a\s+)?file\s+(.+?)\s+containing\s+(.+)$",
        r"^(?:write)\s+(.+?)\s+to\s+(?:the\s+)?file\s+(.+)$",
    ]

    match = re.match(
        patterns[0],
        text,
        re.IGNORECASE
    )

    if match:
        return {
            "tool": "write_file",
            "args": {
                "path": match.group(1).strip(),
                "content": re.sub(
                    r"^exactly\s*:\s*",
                    "",
                    match.group(2).strip(),
                    flags=re.IGNORECASE
                )
            }
        }

    match = re.match(
        patterns[1],
        text,
        re.IGNORECASE
    )

    if match:
        return {
            "tool": "write_file",
            "args": {
                "path": match.group(2).strip(),
                "content": match.group(1).strip()
            }
        }

    # ==================================================
    # LOCAL FILE -> GITHUB CREATE/UPDATE
    # ==================================================

    match = re.match(
        r"^read\s+(.+?)\s+and\s+(?:create|upload|update)\s+(?:it|the\s+file)\s+(?:to|in)\s+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:\s+at\s+(.+?))?(?:\s+on\s+(.+?))?(?:\s+commit\s+message\s*:\s*(.+))?$",
        text,
        re.IGNORECASE
    )

    if match:
        local_path = match.group(1).strip()
        owner = match.group(2).strip()
        repo = match.group(3).strip()
        path = (match.group(4) or Path(local_path).name).strip()
        branch = (match.group(5) or "").strip().rstrip(".,!?")
        message = (match.group(6) or f"Update {path}").strip()

        try:
            content = read_file(os.path.expanduser(local_path))
        except Exception as e:
            return {
                "tool": "run_command",
                "args": {
                    "command": f"cat {local_path}"
                }
            }

        return {
            "tool": "write_github_file",
            "args": {
                "owner": owner,
                "repo": repo,
                "path": path,
                "content": content,
                "message": message,
                "branch": branch or None
            }
        }

    # ==================================================
    # GITHUB CREATE FILE
    # ==================================================

    match = re.match(
        r"^(?:create|make)\s+(?:a\s+)?github\s+file\s+(.+?)\s+in\s+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\s+containing\s+(.+?)(?:\s+commit\s+message\s*:\s*(.+))?$",
        text,
        re.IGNORECASE
    )

    if match:
        path = match.group(1).strip()
        owner = match.group(2).strip()
        repo = match.group(3).strip()
        content = match.group(4).strip()
        message = (
            match.group(5).strip()
            if match.group(5)
            else f"Create {path}"
        )

        return {
            "tool": "write_github_file",
            "args": {
                "owner": owner,
                "repo": repo,
                "path": path,
                "content": content,
                "message": message
            }
        }

    return None


# ==================================================
# SYSTEM PROMPT
# ==================================================

def system_prompt(name, mode):

    return f"""
You are {name}, a practical AI assistant running inside Termux.

IDENTITY:
- Your name is {name}.
- Genei is the overall system name.
- Current mode: {mode}.
- Never claim your name is Genei.

LANGUAGE:
- Speak only English or Roman Urdu.
- Never use Urdu script.
- Never use any other language.

PROJECT:
- Only use the current project's memory and history.
- Never mix information between projects.

TOOLS:
- Never claim an action succeeded unless the tool confirms it.
- Package installation MUST use install_tool.
- Never install packages using run_command.

GITHUB:
- GitHub read requests MUST use the GitHub tools.
- GitHub repository file listing MUST use list_github_files.
- GitHub file reading MUST use read_github_file.
- GitHub file creation or update MUST use write_github_file.
- GitHub file deletion MUST use delete_github_file.
- When the user requests a GitHub file write or deletion, DO NOT ask the user for confirmation in your text response.
- The Python tool layer will handle confirmation before the actual GitHub write or deletion.
- Instead, immediately issue the write_github_file tool call.
- The Python tool layer will handle confirmation before the actual GitHub write.
- Never claim a GitHub write succeeded unless the tool confirms it.
"""


# ==================================================
# PROJECT
# ==================================================

project = current_project()

if not project:
    print("No active project.")
    sys.exit(1)


# ==================================================
# MODE
# ==================================================

args = sys.argv[1:]

mode = None

if args and args[0] in ("--local", "--online"):
    mode = args.pop(0)[2:]

if mode is None:
    mode = DEFAULT_MODE

if mode not in ("local", "online"):
    print(f"Invalid mode: {mode}")
    sys.exit(1)

assistant_name = "Jena" if mode == "local" else "Jeni"


# ==================================================
# PROMPT
# ==================================================

prompt = " ".join(args)

if not prompt:
    print('Usage: genei [--local|--online] "your question"')
    sys.exit(1)


# ==================================================
# IDENTITY
# ==================================================

normalized = prompt.lower().strip().rstrip("?!.") 

if normalized in {
    "what is your name",
    "who are you",
    "what's your name",
    "whats your name"
}:

    answer = f"My name is {assistant_name}."

    add_history(project, "user", prompt)
    add_history(project, "assistant", answer)

    print(answer)
    sys.exit(0)


# ==================================================
# LOCAL MODE
# ==================================================

if mode == "local":

    tool_request = local_tool_request(prompt)

    if tool_request:

        tool_name = tool_request["tool"]
        tool_args = tool_request["args"]

        result = execute_tool(
            tool_name,
            tool_args
        )

        if tool_name == "list_files":

            if isinstance(result, list):

                for item in result:
                    print(item)

            else:
                print(result)

        elif tool_name == "read_file":
            print(result)

        elif tool_name in {
            "write_file",
            "delete_file",
            "install_tool"
        }:
            print(result)

        elif tool_name == "run_command":

            if isinstance(result, dict):

                stdout = result.get("stdout", "")
                stderr = result.get("stderr", "")

                if stdout:
                    print(stdout, end="")

                if stderr:
                    print(stderr, end="")

                if not stdout and not stderr:
                    print(
                        f"Command exited with code "
                        f"{result.get('returncode')}"
                    )

            else:
                print(result)

        else:
            print(result)

        add_history(
            project,
            "user",
            prompt
        )

        add_history(
            project,
            "assistant",
            str(result)
        )

        sys.exit(0)

    history = load_history(project)

    messages = [
        {
            "role": "system",
            "content": system_prompt(
                assistant_name,
                mode
            )
        }
    ]

    messages.extend(history[-20:])

    messages.append({
        "role": "user",
        "content": prompt
    })

    message = local_request(messages)

    answer = message.get(
        "content",
        ""
    )

    add_history(
        project,
        "user",
        prompt
    )

    add_history(
        project,
        "assistant",
        answer
    )

    print(answer)
    sys.exit(0)


# ==================================================
# ONLINE MODE
# ==================================================

install_match = re.match(
    r"^(?:install|add)\s+(?:the\s+)?(?:tool|package)\s+(.+)$",
    prompt.strip(),
    re.IGNORECASE
)

if install_match:

    tool_name = install_match.group(1).strip()

    result = install_tool(tool_name)

    add_history(
        project,
        "user",
        prompt
    )

    add_history(
        project,
        "assistant",
        str(result)
    )

    print(result)
    sys.exit(0)


history = load_history(project)

messages = [
    {
        "role": "system",
        "content": system_prompt(
            assistant_name,
            mode
        )
    }
]

messages.extend(history[-20:])

messages.append({
    "role": "user",
    "content": prompt
})


for _ in range(3):

    message = online_request(messages)

    if "tool_calls" not in message:

        answer = message.get(
            "content",
            ""
        )

        add_history(
            project,
            "user",
            prompt
        )

        add_history(
            project,
            "assistant",
            answer
        )

        print(answer)
        break

    messages.append(message)

    for tool_call in message["tool_calls"]:

        name = tool_call["function"]["name"]

        try:

            tool_args = json.loads(
                tool_call["function"]["arguments"]
            )

        except Exception:

            tool_args = {}

        result = execute_tool(
            name,
            tool_args
        )

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "name": name,
            "content": json.dumps(result)
        })

else:

    print("Maximum tool iterations reached.")
