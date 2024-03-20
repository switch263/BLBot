# Stats Module Documentation

The stats module allows you to track and update statistics for various activities within your Discord bot. It provides functionality to register different modules (cogs) and update their statistics dynamically.

## Registering a Cog

To register a cog, you can use the `register_cog` method from the Stats cog. This method registers the cog with the specified columns for tracking statistics.

For an example of how to register a cog, refer to the example file [here](docs/examples/ping.py).

## Updating Statistics

Once a cog is registered, you can update its statistics using the `update_stats` method. This method allows you to increment or modify the values of specific columns for a given user.

For an example of how to update statistics, refer to the example file [here](docs/examples/ping.py).

