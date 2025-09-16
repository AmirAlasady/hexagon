# MS7/tools/standard_tools/terminal.py

import docker
import time

# Get the Docker client from the environment.
# This will automatically connect to the Docker daemon running on the host.
try:
    client = docker.from_env()
except docker.errors.DockerException:
    print("ERROR: Docker is not running or not configured correctly. The terminal tool will be disabled.")
    client = None

# A simple in-memory dictionary to track user sessions.
# In a multi-instance MS7 setup, this would need to be moved to Redis.
SESSION_CONTAINERS = {}

def get_or_create_container(session_id: str):
    """
    Finds an existing container for a session or creates a new one.
    This function is the core of the sandboxing logic.
    """
    if session_id in SESSION_CONTAINERS:
        container_id = SESSION_CONTAINERS[session_id]['id']
        try:
            container = client.containers.get(container_id)
            # Reset the last-used timestamp
            SESSION_CONTAINERS[session_id]['last_used'] = time.time()
            print(f"Reusing existing container '{container_id}' for session '{session_id}'.")
            return container
        except docker.errors.NotFound:
            print(f"Container '{container_id}' for session '{session_id}' not found. Creating a new one.")
            # The container was stopped or removed, so we'll create a new one.

    # --- Create a new, secure container ---
    # We use a minimal 'alpine' image.
    # We detach it so it runs in the background.
    # We keep it interactive (tty=True) so we can execute commands in it.
    # We set a custom name for easy identification.
    container_name = f"agent-terminal-session-{session_id}"
    print(f"Creating new sandboxed container '{container_name}'...")
    container = client.containers.run(
        "alpine:latest",
        detach=True,
        tty=True,
        name=container_name,
        # For security, we disable networking by default.
        # network_disabled=True, 
        # You could also mount a user-specific, temporary working directory here.
        # volumes={f'/path/to/user/workspaces/{session_id}': {'bind': '/workspace', 'mode': 'rw'}}
    )
    
    SESSION_CONTAINERS[session_id] = {
        'id': container.id,
        'name': container_name,
        'last_used': time.time()
    }
    
    return container

def run_command(command: str, session_id: str) -> str:
    """
    Executes a shell command inside a secure, sandboxed Docker container
    that is unique to the user's session.

    Args:
        command (str): The shell command to execute (e.g., "ls -l", "cat file.txt").
        session_id (str): A unique identifier for the user's conversation or session.

    Returns:
        str: The stdout and stderr from the command execution.
    """
    print(f"EXECUTING TOOL: run_command with command='{command}' for session='{session_id}'")
    
    if not client:
        return "Error: The Docker environment is not available. Terminal tool is disabled."

    try:
        container = get_or_create_container(session_id)
        
        # Execute the command inside the running container.
        exit_code, output = container.exec_run(cmd=f"sh -c '{command}'")
        
        # Decode the output from bytes to a string.
        result = output.decode('utf-8').strip()
        
        if exit_code != 0:
            return f"Error (Exit Code {exit_code}):\n{result}"
        
        # If the command produced no output, provide a confirmation.
        if not result:
            return f"Command '{command}' executed successfully with no output."
            
        return result

    except docker.errors.APIError as e:
        print(f"Docker API Error for session {session_id}: {e}")
        return f"Error: A Docker system error occurred: {e}"
    except Exception as e:
        print(f"An unexpected error occurred in the terminal tool for session {session_id}: {e}")
        return f"Error: An unexpected system error occurred while running the command."

# (Optional: A background thread could be added here to periodically clean up old, inactive containers)