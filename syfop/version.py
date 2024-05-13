import subprocess


def get_version():
    """Get the latest Git tag and prepend 'v' and use the Git comit hash as suffix if the current
    commit has not Git tag."""
    # TODO this will raise an exception if:
    #  - there are no tags
    #  - if it is a shallow clone  with --depth 1
    try:
        git_tag = subprocess.check_output(["git", "describe", "--tags"], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        # TODO I'm giving up on this one. No idea how to do it the right way.
        # readthedocs fails to get the tag if it is more than 50 commits away from HEAD...
        # https://readthedocs.org/projects/syfop/builds/24362900/
        git_tag = "v0.0.0"
        # raise RuntimeError(f"Unable to get version from Git: {e}: {e.output.decode()}")

    # TODO we don't check if the tag is a valid version string (e.g. v0.1.0).
    git_tag = git_tag.decode().strip()
    version = git_tag.lstrip("v")

    # convert string from git-describe to a valid PEP440 version string
    # v0.1.0-4-gc5f364c   -->   syfop-0.1.0.dev4+gc5f364c
    # see: https://stackoverflow.com/a/35522080/859591
    version = version.replace("-", ".dev", 1).replace("-", "+", 1)

    return version


version = get_version()
