# docker-composer-backer-upper

A gloriously-named utility to back up the data volumes of running docker containers that are managed by docker-compose v2.

The utility detects which containers are being run by docker-compose on the current machine. Each running container's YAML file is inspected for local directory mappings, and if any are found, the container is stopped. The directories are backed up to a folder, then the container is restarted. Stopping the containers before copying the files means that there is no possibility of the files being modified during the copy, or held open to prevent the copy taking place. 

[Docker volumes](<https://docs.docker.com/engine/storage/volumes/>) are not backed up, as these may be used by multiple containers, so it would be more difficult to shut all of these down before backing the volumes up.  

The docker-composer-backer-upper is developed using [uv](<https://docs.astral.sh/uv/>). The instructions that follow assume that you have ```uv``` installed. If you don't want to use it, it will hopefully be simple enough to determine how to perform the equivalent actions using your development environment of choice.

## Setup

To generate the required [Pydantic](<https://docs.pydantic.dev/latest/>) model that the backer-upper uses, run the following command in the root repository folder:

```
uv run datamodel-codegen
```

This automatically downloads the latest docker-compose JSON Schema and generates a Python object that will be used to read in compose files for processing.

## Usage

Run using the following command:

```
uv run main <folder to write backups to>
```

By default, up to five backups are kept of each backed up docker volume. If you want to modify this number, use the ```-n``` argument:

```
uv run main -n 10 <folder to write backups to>
```

## Configuration

By default, the backer-upper will look for a file called ```config.toml``` in the same directory as the main script. This can be overridden as follows: 

```
uv run main -c /path/to/my/special_config.toml <folder to write backups to>
```

The default ```config.toml``` file contains comments on which configuration options are available. The options available include:

- A list of exclusion [regexes](<https://regexr.com/>), which will stop volumes from being backed up if matched.
- A list of inclusion regexes, which will force volumes to be backed up if matched, even if they would be matched by an exclusion.

## Contributions Welcome!

If you spot anything that is broken here, or identify any improvements, please submit a PR or open an issue, and I'll do my best to take a look in a reasonable timeframe (real-life workload permitting).

## License

This project is licensed under

 * MIT license ([LICENSE-MIT](LICENSE) or
   https://opensource.org/licenses/MIT)
