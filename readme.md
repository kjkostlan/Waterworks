## Waterworks: Handles the stuff outside your Python program itself.

This project is somewhere between alpha and beta.

The main feature is the MessyPipe class: an interface to work with various streams,
most notably other process streams and SSH streams.

Other features:
1. A "plumber" class that helps debug communication with unreliable SSH processes.
2. A python updater tool, if changes are made while the program is running.
3. Simplified module path handling, for example to import Python code from an external folder.
4. More convenient file_io functions.
5. Basic IP address wrangling features. This does NOT include creating/destroying vm and other heavy cloud operations. Skythonic does that.
