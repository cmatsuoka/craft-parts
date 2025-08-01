.. _craft_parts_rust_plugin:

Rust plugin
=============

The Rust plugin can be used for Rust projects that use the Cargo build system.

Keys
----

This plugin provides the following unique keys.

rust-channel
~~~~~~~~~~~~
**Type:** string
**Default:** stable

Used to select which `Rust channel or version <https://rust-lang.github.io/rustup/concepts/channels.html#channels>`_ to use.
It can be one of "stable", "beta", "nightly" or a version number.
If you want to use a specific nightly version, use this format:
``"nightly-YYYY-MM-DD"``.
If you don't want this plugin to install Rust toolchain for you,
you can put ``"none"`` for this option.

.. _rust-features:

rust-features
~~~~~~~~~~~~~
**Type:** list of strings

Features used to build optional dependencies.
This is equivalent to the ``--features`` option in Cargo.

You can also use ``["*"]`` to select all the features available in the project.

.. note::
  This option does not override any default features
  specified by the project itself.

  If you want to override the default features, please see the :ref:`rust-no-default-features`
  option below.

.. _rust-no-default-features:

rust-no-default-features
~~~~~~~~~~~~~~~~~~~~~~~~~~
**Type:** boolean
**Default:** false

If this option is set to ``true``, the default features specified by the project
will be ignored.

You can then use the :ref:`rust-features` key to specify any features you wish to override.

rust-path
~~~~~~~~~
**Type:** list of strings
**Default:** .

The path to the package root (that contains the ``Cargo.toml`` file).
This is equivalent to the ``--manifest-path`` option in Cargo.

.. _rust-use-global-lto:

rust-use-global-lto
~~~~~~~~~~~~~~~~~~~
**Type:** boolean
**Default:** false

Whether to use global LTO.
This option may significantly impact the build performance but
reducing the final binary size and improve the runtime performance.
This will forcibly enable LTO for all the crates you specified,
regardless of whether the projects have the LTO option enabled
in the Cargo.toml file.

This is equivalent to the ``lto = "fat"`` option in the Cargo.toml file.

If you want better runtime performance, see the :ref:`Performance tuning<perf-tuning>` section below.

rust-ignore-toolchain-file
~~~~~~~~~~~~~~~~~~~~~~~~~~
**Type:** boolean
**Default:** false

Whether to ignore the ``rust-toolchain.toml`` and ``rust-toolchain`` file.
The upstream project can use this file to specify which Rust
toolchain to use and which component to install.
If you don't want to follow the upstream project's specifications,
you can put true for this option to ignore the toolchain file.

rust-cargo-parameters
~~~~~~~~~~~~~~~~~~~~~
**Type:** list of strings
**Default:** []

Append additional parameters to the Cargo command line.

rust-inherit-ldflags
~~~~~~~~~~~~~~~~~~~~~
**Type:** boolean
**Default:** false

Whether to inherit the LDFLAGS from the environment.
This option will add the LDFLAGS from the environment to the
Rust linker directives.

Cargo build system and Rust compiler by default do not respect the ``LDFLAGS``
environment variable. This option will cause the craft-parts plugin to
forcibly add the contents inside the ``LDFLAGS`` to the Rust linker directives
by wrapping and appending the ``LDFLAGS`` value to ``RUSTFLAGS``.

.. note::
  You may use this option to tune the Rust binary in a classic Snap to respect
  the Snap linkage, so that the binary will not find the libraries in the host
  filesystem.

  Here is an example on how you might do this on core24:

  .. code-block:: yaml

        parts:
          my-classic-app:
            plugin: rust
            source: .
            rust-inherit-ldflags: true
            build-environment:
              - LDFLAGS: >
                  -Wl,-rpath=\$ORIGIN/lib:/snap/core24/current/lib/$CRAFT_ARCH_TRIPLET_BUILD_FOR
                  -Wl,-dynamic-linker=$(find /snap/core24/current/lib/$CRAFT_ARCH_TRIPLET_BUILD_FOR -name 'ld*.so.*' -print | head -n1)


Environment variables
---------------------

This plugin sets the PATH environment variable so the Rust compiler is accessible in the build environment.

Some environment variables may also influence the Rust compiler or Cargo build tool.
For more information, see `Cargo documentation <https://doc.rust-lang.org/cargo/reference/environment-variables.html>`_ for the details.

Dependencies
------------

By default this plugin uses Rust toolchain binaries from the Rust upstream.
If this is not desired, you can set ``rust-deps: ["rustc", "cargo"]`` and
``rust-channel: "none"`` in the part definition to override the default behaviour.

.. _perf-tuning:

Performance tuning
-------------------

.. warning::
  Keep in mind that due to individual differences between different projects, some of the
  optimisations may not work as expected or even incur performance penalties. YMMV.

  Some programs may even behave differently or crash if aggressive optimisations are used.

Many Rust programs boast their performance over similar programs implemented in other
programming languages.
To get even better performance, you might want to follow the tips below.

* Use the :ref:`rust-use-global-lto` option to enable LTO support. This is suitable for most
  projects. However, analysing the whole program during the build time requires more memory and CPU time.

* Specify ``codegen-units=1`` in ``Cargo.toml`` to reduce LLVM parallelism. This may sound counter-intuitive,
  but reducing code generator threads could improve the quality of generated machine code.
  This option will also reduce the build time performance since the code generator uses only one thread per translation unit.

* Disable ``incremental=true`` in ``Cargo.toml`` to improve inter-procedural optimisations. Many projects may have
  already done this for the release profile. You should check if that is the case for your project.

* (Advanced) Perform cross-language LTO. This requires installing the correct version of LLVM/Clang and setting the right environment variables.
  You must know which LLVM version of your selected Rust toolchain is using.
  You can use ``rustc -vV`` to check the LLVM version used by the compiler. For example, you can see Rust 1.81 uses LLVM 18.1 because
  it prints an output like this:

  .. terminal::
    :input: rustc -vV
    :user: dev
    :host: ubuntu

    rustc 1.81.0 (eeb90cda1 2024-09-04)
    binary: rustc
    commit-hash: eeb90cda1969383f56a2637cbd3037bdf598841c
    commit-date: 2024-09-04
    host: x86_64-unknown-linux-gnu
    release: 1.81.0
    LLVM version: 18.1.7

  On Rust toolchains that don't include the LLVM version, you can check the LLVM version number by examining the ``lib`` directory.
  For example, Rust 1.81 uses LLVM 18.1 because it bundles a ``libLLVM.so.18.1-rust-1.81.0-stable`` file under the ``lib`` directory.
  In this case, you would install ``clang-18`` and ``lld-18`` from the Ubuntu archive.

  * You will need to set these environment variables for Clang:
      .. code-block:: yaml

        parts:
          my-app:
            plugin: rust
            source: .
            build-packages:
              - clang-18
              - lld-18
            build-environment:
              - CC: clang-18
              - CXX: clang++-18
              - CFLAGS: -flto=full -O3
              - CXXFLAGS: -flto=full -O3
              - RUSTFLAGS: "-Cembed-bitcode=yes -Clinker-plugin-lto -Clinker=clang-18 -Clink-arg=-flto=full -Clink-arg=-fuse-ld=lld -Clink-arg=-Wl,--lto-O3"

    For some projects that manipulate the object files during the build, you may also need:
      .. code-block:: bash

        export NM=llvm-nm-18
        export AR=llvm-ar-18
        export RANLIB=llvm-ranlib-18

    You can refer to the `rustc documentation <https://doc.rust-lang.org/rustc/codegen-options/index.html>`_ for more information on the meaning of those options.
  * You will need significantly more memory and CPU time for large projects to build and link.
    For instance, Firefox under full LTO requires about 80 GiB of memory to pass the linking phase.
