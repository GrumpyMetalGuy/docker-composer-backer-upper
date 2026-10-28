# docker-composer-backer-upper

A gloriously-named utility to back up the data volumes of running docker containers that are managed by docker-compose
v2.

The utility detects which containers are being run by docker-compose on the current machine. Each running container's
YAML file is inspected for local directory mappings, and if any are found, the container is stopped. The directories are
backed up to a zipped tarfile, then the container is restarted. Stopping the containers before copying the files means
that there is no possibility of the files being modified during the copy, or held open to prevent the copy taking place.

[Docker volumes](<https://docs.docker.com/engine/storage/volumes/>) are not backed up, as these may be used by multiple
containers, so it would be more difficult to shut all of these down before backing the volumes up.

The docker-composer-backer-upper is developed using [uv](<https://docs.astral.sh/uv/>). The instructions that follow
assume that you have ```uv``` installed. If you don't want to use it, it will hopefully be simple enough to determine
how to perform the equivalent actions using your development environment of choice.

## Setup

To generate the required [Pydantic](<https://docs.pydantic.dev/latest/>) model that the backer-upper uses, run the
following command in the root repository folder:

```
uv run datamodel-codegen
```

This automatically downloads the latest docker-compose JSON Schema and generates a Python object that will be used to
read in compose files for processing.

## Usage

Run using the following command:

```
uv run main
```

If you'd like to specify a different config file to the one included, use the ```-c``` option:

```
uv run main -c <path to config file>
```

You can perform a dry run without copying any data by using the -```d``` option:

```
uv run main -d
```

By default, the backer-upper fails the backup for a service if any of its files cannot be read (for example a
permission error). To instead continue and produce a best-effort archive, pass the ```-i``` option:

```
uv run main -i
```

You can also control this behaviour per service using the ```[services]``` section in the config file (see below).

## Configuration

Before running, copy ```config.toml.example``` to ```config.toml``` and edit it to suit. The backer-upper always loads
```config.toml``` from the same directory as the main script (or the file given with ```-c```). ```config.toml``` is
git-ignored, so your custom settings survive pulls. The example file contains comments on which configuration options are
available. The options available are:

- The backup folder location.
- A list of docker-compose file exclusions, which will exclude any running docker-compose containers using these
  filenames.
- A list of volume exclusion [regexes](<https://regexr.com/>), which will stop volumes from being backed up if matched.
- A list of volume inclusion regexes, which will force volumes to be backed up if matched, even if they would be matched
  by an exclusion.
- The number of folder backups to keep.

## Per-service error handling

By default, a copy error (such as a permission problem) fails the backup for that service and makes the run exit with a
non-zero status. The container is still restarted. If you care less about some containers, you can tell the backer-upper
to tolerate unreadable files for those services and keep a best-effort backup.

Use the ```[services]``` table in ```config.toml```, keyed by the service or container name. Set ```ignore_errors``` to
```true``` to ignore copy errors, or ```false``` to fail on them:

```toml
[services.mysql]
ignore_errors = true

[services.postgres]
ignore_errors = false
```

A service that is not listed falls back to the ```-i``` flag (off by default). The ```-i``` flag and a service's own
setting combine as: the service setting wins, otherwise the flag, otherwise fail.

## Excluding a service

Mark a service with the `dcbu.exclude` annotation to skip it entirely. It will not be stopped or backed up.
Either annotation syntax works:

```yaml
services:
  db:
    image: postgres:16
    annotations:
      dcbu.exclude: "true"
```

```yaml
services:
  db:
    image: postgres:16
    annotations:
      - dcbu.exclude=true
```

## Contributions Welcome!

If you spot anything that is broken here, or identify any improvements, please submit a PR or open an issue, and I'll do
my best to take a look in a reasonable timeframe (real-life workload permitting).

## License

This project is licensed under

* MIT license ([LICENSE-MIT](LICENSE) or
  https://opensource.org/licenses/MIT)
