# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2015-2021 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Implement the git source handler."""

import os
import re
import subprocess
import sys
from typing import List, Optional

from craft_parts.dirs import ProjectDirs

from . import errors
from .base import SourceHandler


class GitSource(SourceHandler):
    """The git source handler."""

    @classmethod
    def version(cls) -> str:
        """Get git version information."""
        return (
            subprocess.check_output(["git", "version"], stderr=subprocess.DEVNULL)
            .decode(sys.getfilesystemencoding())
            .strip()
        )

    @classmethod
    def check_command_installed(cls) -> bool:
        """Check if git is installed."""
        try:
            cls.version()
        except FileNotFoundError:
            return False
        return True

    @classmethod
    def generate_version(cls, *, part_src_dir=None):
        """Return the latest git tag from PWD or defined part_src_dir.

        The output depends on the use of annotated tags and will return
        something like: '2.28+git.10.abcdef' where '2.28 is the
        tag, '+git' indicates there are commits ahead of the tag, in
        this case it is '10' and the latest commit hash begins with
        'abcdef'. If there are no tags or the revision cannot be
        determined, this will return 0 as the tag and only the commit
        hash of the latest commit.
        """
        if not part_src_dir:
            part_src_dir = os.getcwd()

        encoding = sys.getfilesystemencoding()
        try:
            output = (
                subprocess.check_output(
                    ["git", "-C", part_src_dir, "describe", "--dirty"],
                    stderr=subprocess.DEVNULL,
                )
                .decode(encoding)
                .strip()
            )
        except subprocess.CalledProcessError as err:
            # If we fall into this exception it is because the repo is not
            # tagged at all.
            proc = subprocess.Popen(
                ["git", "-C", part_src_dir, "describe", "--dirty", "--always"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                # This most likely means the project we are in is not driven
                # by git.
                raise errors.VCSError(message=stderr.decode(encoding).strip()) from err
            return "0+git.{}".format(stdout.decode(encoding).strip())

        match = re.search(
            r"^(?P<tag>[a-zA-Z0-9.+~-]+)-"
            r"(?P<revs_ahead>\d+)-"
            r"g(?P<commit>[0-9a-fA-F]+(?:-dirty)?)$",
            output,
        )

        if not match:
            # This means we have a pure tag
            return output

        tag = match.group("tag")
        revs_ahead = match.group("revs_ahead")
        commit = match.group("commit")

        return "{}+git{}.{}".format(tag, revs_ahead, commit)

    def __init__(  # pylint: disable=too-many-arguments
        self,
        source,
        part_src_dir,
        *,
        application_name: str = None,
        source_tag: str = None,
        source_commit: str = None,
        source_branch: str = None,
        source_depth: Optional[int] = None,
        silent: bool = False,
        source_checksum: str = None,
        project_dirs: ProjectDirs = None,
    ):
        super().__init__(
            source,
            part_src_dir,
            application_name=application_name,
            source_tag=source_tag,
            source_commit=source_commit,
            source_branch=source_branch,
            source_depth=source_depth,
            source_checksum=source_checksum,
            project_dirs=project_dirs,
            command="git",
        )

        if not self.command:
            raise RuntimeError("command not specified")

        if source_tag and source_branch:
            raise errors.IncompatibleSourceOptions(
                "git", ["source-tag", "source-branch"]
            )
        if source_tag and source_commit:
            raise errors.IncompatibleSourceOptions(
                "git", ["source-tag", "source-commit"]
            )
        if source_branch and source_commit:
            raise errors.IncompatibleSourceOptions(
                "git", ["source-branch", "source-commit"]
            )
        if source_checksum:
            raise errors.InvalidSourceOption(
                source_type="git", option="source-checksum"
            )
        self._call_kwargs = {}
        if silent:
            self._call_kwargs["stdout"] = subprocess.DEVNULL
            self._call_kwargs["stderr"] = subprocess.DEVNULL

    def _fetch_origin_commit(self):
        command = [
            self.command,
            "-C",
            self.part_src_dir,
            "fetch",
            "origin",
        ]
        if self.source_commit:
            command.append(self.source_commit)

        self._run(command, **self._call_kwargs)

    def _pull_existing(self):
        refspec = "HEAD"
        if self.source_branch:
            refspec = "refs/heads/" + self.source_branch
        elif self.source_tag:
            refspec = "refs/tags/" + self.source_tag
        elif self.source_commit:
            refspec = self.source_commit
            self._fetch_origin_commit()

        reset_spec = refspec if refspec != "HEAD" else "origin/master"

        command = [
            self.command,
            "-C",
            self.part_src_dir,
            "fetch",
            "--prune",
            "--recurse-submodules=yes",
        ]
        self._run(command, **self._call_kwargs)

        command = [self.command, "-C", self.part_src_dir, "reset", "--hard"]
        if reset_spec:
            command.append(reset_spec)

        self._run(command, **self._call_kwargs)

        # Merge any updates for the submodules (if any).
        command = [
            self.command,
            "-C",
            self.part_src_dir,
            "submodule",
            "update",
            "--recursive",
            "--force",
        ]
        self._run(command, **self._call_kwargs)

    def _clone_new(self):
        command = [self.command, "clone", "--recursive"]
        if self.source_tag or self.source_branch:
            command.extend(["--branch", self.source_tag or self.source_branch])
        if self.source_depth:
            command.extend(["--depth", str(self.source_depth)])
        self._run(command + [self.source, self.part_src_dir], **self._call_kwargs)

        if self.source_commit:
            self._fetch_origin_commit()
            command = [
                self.command,
                "-C",
                self.part_src_dir,
                "checkout",
                self.source_commit,
            ]
            self._run(command, **self._call_kwargs)

    def is_local(self):
        """Verify whether the git repository is on the local filesystem."""
        return os.path.exists(os.path.join(self.part_src_dir, ".git"))

    def pull(self):
        """Retrieve the local or remote source files."""
        if self.is_local():
            self._pull_existing()
        else:
            self._clone_new()
        self.source_details = self._get_source_details()

    def push(self, url, refspec, force=False):
        """Push the source git repository to the specified URL."""
        command = [self.command, "-C", self.part_src_dir, "push", url, refspec]

        if force:
            command.append("--force")

        _run_git_command(command)

    def init(self):
        """Initialize the source git repository."""
        command = [self.command, "-C", self.part_src_dir, "init"]
        _run_git_command(command)

    def add(self, file):
        """Add a file to the source git repository."""
        if file.startswith(self.part_src_dir):
            file = os.path.relpath(file, self.part_src_dir)

        command = [self.command, "-C", self.part_src_dir, "add", file]
        _run_git_command(command)

    def commit(self, message, author="snapcraft <snapcraft@snapcraft.local>"):
        """Commit changes to the source git repository."""
        command = [
            self.command,
            "-C",
            self.part_src_dir,
            "commit",
            "--no-gpg-sign",
            "--message",
            message,
            "--author",
            author,
        ]
        _run_git_command(command)

    def _get_source_details(self):
        tag = self.source_tag
        commit = self.source_commit
        branch = self.source_branch
        source = self.source
        checksum = self.source_checksum

        if not tag and not branch and not commit:
            commit = self._run_output(
                ["git", "-C", self.part_src_dir, "rev-parse", "HEAD"]
            )

        return {
            "source-commit": commit,
            "source-branch": branch,
            "source": source,
            "source-tag": tag,
            "source-checksum": checksum,
        }


def _run_git_command(command: List[str]) -> None:
    try:
        subprocess.check_output(command)
    except subprocess.CalledProcessError as error:
        raise errors.GitCommandError(
            command=command,
            exit_code=error.returncode,
            output=error.output.decode(),
        )
