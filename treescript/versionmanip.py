#!/usr/bin/env python
"""Treescript version manipulation."""

from distutils.version import StrictVersion, LooseVersion
import logging
import os

from treescript.exceptions import TaskVerificationError, BumpVerificationError
from treescript.mercurial import run_hg_command
from treescript.task import get_version_bump_info

log = logging.getLogger(__name__)


ALLOWED_BUMP_FILES = (
    'browser/config/version.txt',
    'browser/config/version_display.txt',
    'config/milestone.txt'
)


def _get_version(file):
    """Parse the version from file."""
    log.info("Reading {} for version information.".format(file))
    with open(file, 'r') as f:
        contents = f.read()
    log.info("Contents:")
    for line in contents.splitlines():
        log.info(" {}".format(line))
    lines = [l for l in contents.splitlines() if l and
             not l.startswith("#")]
    return lines[-1]


async def bump_version(context):
    """Perform a version bump.

    This function takes its inputs from context.task by using the ``get_version_bump_info``
    function from treescript.task. Using `next_version` and `files`.

    This function does nothing (but logs) if the current version and next version
    match, and nothing if the next_version is actually less than current_version.

    raises:
        TaskverificationError: if a file specified is not allowed, or
                               if the file is not in the target repository.

    """
    bump_info = get_version_bump_info(context.task)
    next_version = bump_info['next_version']
    old_next_version = None
    files = bump_info['files']
    changed = False
    for file in files:
        if old_next_version:
            next_version = old_next_version
        abs_file = os.path.join(context.repo, file)
        if file not in ALLOWED_BUMP_FILES:
            raise TaskVerificationError("Specified file to version bump is not in whitelist")
        if not os.path.exists(abs_file):
            raise TaskVerificationError("Specified file is not in repo")
        curr_version = _get_version(abs_file)

        Comparator = StrictVersion
        if curr_version.endswith('esr') or next_version.endswith('esr'):
            #  We use LooseVersion for ESR because StrictVersion can't parse the trailing
            # 'esr', but StrictVersion otherwise because it can sort X.0bN lower than X.0
            Comparator = LooseVersion
        if Comparator(next_version) < Comparator(curr_version):
            log.warning("Version bumping skipped due to conflicting values: "
                        "(next version {} is < current version {})"
                        .format(next_version, curr_version)
                        )
            continue
        elif Comparator(next_version) == Comparator(curr_version):
            log.info("Version bumping skipped due to unchanged values")
            continue
        else:
            changed = True
            if curr_version.endswith('esr'):
                # Only support esr addition if already an esr string.
                if not next_version.endswith('esr'):
                    old_next_version = next_version
                    next_version = next_version + 'esr'
            replace_ver_in_file(file=abs_file,
                                curr_version=curr_version, new_version=next_version)
            verify_version = _get_version(abs_file)
            if Comparator(verify_version) != Comparator(next_version):
                log.error("Version bump failed! Intended %s, actual: %s in %s", next_version, verify_version, abs_file)
                raise BumpVerificationError("Version bump failed! Intended {}, actual: {} in {}".format(next_version, verify_version, abs_file))
    if changed:
        commit_msg = 'Automatic version bump CLOSED TREE NO BUG a=release'
        await run_hg_command(context, 'commit', '-m', commit_msg,
                             local_repo=context.repo)


def replace_ver_in_file(file, curr_version, new_version):
    """Read in contents of `file` and then update version.

    Implementation detail: replaces instances of `curr_version` with `new_version`
    using python3 str.replace().

    raises:
        Exception: if contents before and after match.

    """
    with open(file, 'r') as f:
        contents = f.read()
    new_contents = contents.replace(curr_version, new_version)
    if contents == new_contents:
        raise Exception("Did not expect no changes")
    with open(file, 'w') as f:
        f.write(new_contents)


async def verify_bump(context):
    """Verify that a version bump has been applied."""
    bump_info = get_version_bump_info(context.task)
    next_version = bump_info['next_version']
    files = bump_info['files']
    for file in files:
        abs_file = os.path.join(context.repo, file)
        if file not in ALLOWED_BUMP_FILES:
            raise TaskVerificationError("Specified file to version bump is not in whitelist")
        if not os.path.exists(abs_file):
            raise TaskVerificationError("Specified file is not in repo")
        curr_version = _get_version(abs_file)

        Comparator = StrictVersion
        if curr_version.endswith('esr') or next_version.endswith('esr'):
            #  We use LooseVersion for ESR because StrictVersion can't parse the trailing
            # 'esr', but StrictVersion otherwise because it can sort X.0bN lower than X.0
            Comparator = LooseVersion
        if Comparator(curr_version) != Comparator(next_version):
            raise BumpVerificationError("Version bump failed! Intended {}, actual: {} in {}".format(next_version, curr_version, abs_file))
