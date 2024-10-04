# docker-composer-backer-upper

A gloriously-named utility to back up running docker containers that are managed by docker-compose v2.

The utility attempts to determine which docker-compose YAML scripts are being run on the current machine. Each running container's YAML file is inspected for local directory mappings, and if any are found, the container is stopped. The directories are backed up to a folder, then the container is restarted.

The docker-composer-backer-upper is developed using [uv](<https://docs.astral.sh/uv/>). The instructions that follow assume that you have ```uv``` installed. If you don't want to use it, it will hopefully be simple enough to determine how to perform the equivalent actions using your development environment of choice.

## Setup

To generate the required [Pydantic](<https://docs.pydantic.dev/latest/>) model that the backer-upper uses, run the following command in the root repository folder:

```
uv run datamodel-codegen
```

This automatically downloads the latest docker-compose JSON Schema and generates  will create a Python object that will be used to read in compose files for processing.

## Usage

Run using the following command:

```
uv run main <folder to write backups to>
```

By default, up to five backups are kept of each backed up docker volume. If you want to modify this number, use the ```-n``` argument:

```
uv run main -n 10 <folder to write backups to>
```

## Volume Exclusions

There is a list of volume entries that are ignored when performing backups. This can be found in the ```COMMON_EXCLUSIONS``` set at the top of ```main.py```. If you have any specific folders or files that you want to ignore, these can be added here. This may end up being parameterised in a later version if this is of use.

## Contributons Welcome!

If you spot anything that is broken here, or identify any improvements, please submit a PR or open an issue, and I'll do my best to take a look in a reasonable timeframe (real-life workload permitting).

## License

This project is licensed under

 * MIT license ([LICENSE-MIT](LICENSE-MIT) or
   https://opensource.org/licenses/MIT)
