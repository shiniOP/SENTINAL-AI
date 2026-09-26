import requests
from urllib.parse import urlparse


def normalize_repo(repo: str) -> str:
    """
    Convert different GitHub repository formats into:

        owner/repository
    """

    repo = repo.strip()

    # Full GitHub URL
    if repo.startswith("http://") or repo.startswith("https://"):

        parsed = urlparse(repo)

        if parsed.netloc.lower() not in {
            "github.com",
            "www.github.com",
        }:
            raise ValueError(
                "Repository URL must be from github.com"
            )

        repo = parsed.path.strip("/")

    # Remove .git
    if repo.endswith(".git"):
        repo = repo[:-4]

    parts = repo.split("/")

    if len(parts) != 2 or not all(parts):
        raise ValueError(
            "Invalid GitHub repository. "
            "Use owner/repository or a GitHub repository URL."
        )

    return f"{parts[0]}/{parts[1]}"


def get_recent_commits(
    repo: str,
    per_page: int = 5
):

    try:

        repo = normalize_repo(repo)

    except ValueError as e:

        return {
            "success": False,
            "error": str(e),
        }

    url = (
        f"https://api.github.com/repos/"
        f"{repo}/commits"
    )

    params = {
        "per_page": per_page
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=10,
        )

    except requests.Timeout:

        return {
            "success": False,
            "error": "GitHub API request timed out",
        }

    except requests.RequestException as e:

        return {
            "success": False,
            "error": (
                f"GitHub API request failed: {str(e)}"
            ),
        }

    if response.status_code != 200:

        return {
            "success": False,
            "status_code": response.status_code,
            "error": response.text,
        }

    try:

        data = response.json()

    except ValueError:

        return {
            "success": False,
            "status_code": response.status_code,
            "error": "GitHub returned invalid JSON",
        }

    if not isinstance(data, list):

        return {
            "success": False,
            "status_code": response.status_code,
            "error": (
                "Unexpected GitHub API response format"
            ),
        }

    commits = []

    for commit in data:

        commit_data = commit.get(
            "commit",
            {}
        )

        author = commit_data.get(
            "author",
            {}
        )

        commits.append({
            "sha": commit.get("sha"),
            "message": commit_data.get("message"),
            "author": author.get("name"),
            "date": author.get("date"),
        })

    return {
        "success": True,
        "status_code": response.status_code,
        "repository": repo,
        "commits": commits,
    }