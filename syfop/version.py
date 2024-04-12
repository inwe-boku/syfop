import subprocess


def get_version():
    """Get the latest Git tag and prepend 'v' and use the Git comit hash as suffix if the current
    commit has not Git tag."""
    git_tag = subprocess.check_output(["git", "describe", "--tags"]).decode().strip()
    version = git_tag.lstrip("v")

    # convert string from git-describe to a valid PEP440 version string
    # v0.1.0-4-gc5f364c   -->   syfop-0.1.0.dev4+gc5f364c
    # see: https://stackoverflow.com/a/35522080/859591
    version = version.replace("-", ".dev", 1).replace("-", "+", 1)

    return version


version = get_version()
