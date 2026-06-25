import os
import sys
import urllib.request


def main() -> int:
    url = os.getenv("HEALTHCHECK_URL", "http://127.0.0.1:8000/health/?format=text")
    request = urllib.request.Request(url, headers={"X-Forwarded-Proto": "https"})
    with urllib.request.urlopen(request, timeout=5) as response:
        if 200 <= response.status < 400:
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
