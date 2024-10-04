# docker-composer-backer-upper

A utility to back up running docker containers that are managed by docker-compose.

## Setup

To generate the required Pydantic model that the backer-upper uses, run the following command:

```commandline
uv run datamodel-codegen
```

This will create a Python object that will be used to read in compose files for processing.

## Usage

Run using the following command:

```commandline
uv run main <source docker-compse config folder> <folder to write backups to>
```
