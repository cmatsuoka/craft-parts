.. _craft_parts_dump_plugin:

Dump plugin
=============

The Dump plugin can be used for any project where you want to include existing
files from somewhere and keep the content as is. Its source can be a local
directory, a remote repository, or a URL. Common use cases include:

- Include static files like scripts or media from a local directory.
- Download and unpack pre-compiled proprietary software from a remote URL.
- Use git to clone a remote SDK, dataset, or model.


Keys
----

This plugin has no unique keys.

You must specify at least the ``source`` key. The ``source-type`` key is optional, but
recommended, as it is used to specify how the source should be handled.


Dependencies
------------

This plugin has no dependencies.


How it works
------------

During the build step, the plugin performs the following actions:

* Check the ``source-type`` key to determine the type of the source if
  specified, otherwise, it will try to guess the type based on the ``source``.
* Download the file or clone the repository if the ``source`` is a remote
  location.
* Copy the file or directory if the ``source`` is a local location.
* Unpack the file if it is an archive specified by the ``source-type`` key.
* Copy all contents and preserve the directory structure to the part's install
  directory.
