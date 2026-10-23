import argparse
import collections.abc
import contextlib
import json
import os
import re
import shutil
import sys
import tarfile

import docker
import toml
import yaml
from docker_composer import DockerCompose, base
from loguru import logger

from compose_model import ComposeSpecification, Volumes

logger = logger.patch(lambda record: record.update(name='docker-composer-backer-upper'))


def _get_docker_compose_object(args: argparse.Namespace, *command_args, **command_kwargs) -> DockerCompose:
	"""
	Helper function to return docker compose object, initialised with the correct docker compose command.

	:param args: Program arguments
	:param command_args: args to pass to the docker compose object.
	:param command_kwargs: kwargs to pass to the docker compose object
	:return: Docker compose object.
	"""
	docker_compose_instance = DockerCompose(*command_args, **command_kwargs)

	if args.new_command:
		logger.info('Forcing use of "docker compose" instead of "docker-compose')
		docker_compose_instance._parent_cmd = ['docker', 'compose']

	return docker_compose_instance


def _get_compose_files() -> collections.abc.Iterable[str]:
	"""
	Return a list of docker compose files to process.

	:return: List of filenames for running docker compose files.
	"""

	compose_config_files = set()

	docker_client = docker.from_env()

	for container in docker_client.containers.list():
		if container.status == 'running':
			if config_files := container.labels.get('com.docker.compose.project.config_files'):
				compose_config_files.update(config_files.split(','))

	return compose_config_files


def _get_compose_model(compose_filename: str) -> ComposeSpecification:
	"""
	For a given docker compose filename, attempt to build a docker-compose Model object from it.

	:param compose_filename: docker-compose file to generate model for.
	:return: Pydantic object representing a docker-compose file.
	"""
	with open(compose_filename) as handle:
		compose_file_contents = handle.read()

	# Simple conversion from YAML -> JSON, other libs exist for this purpose, but we'll keep it simple for now
	yaml_obj = yaml.safe_load(compose_file_contents)
	json_str = json.dumps(yaml_obj)

	return ComposeSpecification.model_validate_json(json_str)


def _backup_volumes(args: argparse.Namespace, config: dict, service_name: str, volumes: set[str]):
	target_backup_file = os.path.join(config['backup_folder'], f'{service_name}.tgz')

	number_of_backups = config.get('number_backups', 2)
	is_dry_run = args.dry_run

	if not is_dry_run:
		os.makedirs(config['backup_folder'], exist_ok=True)

		for backup_counter in range(number_of_backups, 0, -1):
			potential_backup_file = f'{target_backup_file}.{backup_counter}'

			if os.path.exists(potential_backup_file):
				# If it's the oldest kept backup, drop it; otherwise shift it up one slot.
				if backup_counter == number_of_backups:
					os.remove(potential_backup_file)
				else:
					shutil.move(potential_backup_file, f'{target_backup_file}.{backup_counter + 1}')

		if os.path.exists(target_backup_file):
			shutil.move(target_backup_file, f'{target_backup_file}.1')

	if is_dry_run:
		target_file_context = contextlib.nullcontext()
	else:
		target_file_context = tarfile.open(target_backup_file, 'w:gz')

	with target_file_context:
		for volume in volumes:
			if os.path.exists(volume):
				try:
					if is_dry_run:
						logger.info(f'Would have copied from {volume} to {target_backup_file}')
					else:
						logger.info(f'Copying from {volume} to {target_backup_file}')

						target_file_context.add(volume, arcname=volume.lstrip('/'))
				except Exception as e:
					logger.error(f'Error copying files: {e}')


# Annotation key that marks a service as excluded from backup.
EXCLUDE_ANNOTATION = 'dcbu.exclude'


def _bind_host_path(volume: str | Volumes) -> str | None:
	"""
	Return the host-side path for a bind mount, or None for non-bind volumes.

	Short-form string volumes are "SOURCE:TARGET[:MODE]"; long-form entries are Volumes
	mappings whose bind source we only report when type is bind.
	"""
	if isinstance(volume, Volumes):
		if volume.type != 'bind':
			return None

		return volume.source

	source = volume.split(':')[0]

	if source.startswith(('/', './', '../', '~')):
		return source

	return None


def _service_excluded(service) -> bool:
	"""
	Return True if a service declares the exclude annotation.

	Annotations may be a mapping of key/value pairs or a list of "key=value" strings.
	"""
	annotations = service.annotations

	if not annotations:
		return False

	if isinstance(annotations, dict):
		return EXCLUDE_ANNOTATION in annotations

	return any(item.split('=')[0] == EXCLUDE_ANNOTATION for item in annotations.root)


def _process_compose_file(compose_filename: str, args: argparse.Namespace, config: dict):
	compose_model = _get_compose_model(compose_filename)

	volumes_to_backup = {}

	exclusions = set(config.get('volume_exclusions', []))
	inclusions = set(config.get('volume_inclusions', []))
	exclusion_res = [re.compile(e) for e in exclusions]
	inclusion_res = [re.compile(i) for i in inclusions]

	for service_name, service in (compose_model.services or {}).items():
		if _service_excluded(service):
			logger.info(f'Skipping service {service_name}: marked with {EXCLUDE_ANNOTATION}')
			continue

		compose_file_volumes = set()

		for volume in service.volumes or []:
			volume = _bind_host_path(volume)

			if not volume:
				continue

			# First, look for forced inclusions
			if any(i.match(volume) for i in inclusion_res):
				compose_file_volumes.add(volume)
				continue

			# Otherwise, check if the volume is excluded.
			if not any(e.match(volume) for e in exclusion_res):
				compose_file_volumes.add(volume)

		if compose_file_volumes:
			volumes_to_backup[service.container_name or service_name] = compose_file_volumes

	if volumes_to_backup:
		docker_compose_instance = _get_docker_compose_object(args, file=compose_filename)

		try:
			if args.dry_run:
				logger.info(f'Would have stopped docker-compose file {compose_filename}')
			else:
				down_results_raw = docker_compose_instance.down().call(capture_output=True)

				if down_results_raw.returncode != 0:
					logger.warning(
						f'Error stopping docker-compose file {compose_filename}, return code was {down_results_raw.returncode}'
					)

			for service_name, volumes in volumes_to_backup.items():
				_backup_volumes(args, config, service_name, volumes)
		except:
			logger.exception(f'Attempting to bring down {compose_filename} and copy volumes')
		finally:
			if not args.dry_run:
				up_results_raw = docker_compose_instance.up(detach=True).call(capture_output=True)

				if up_results_raw.returncode != 0:
					logger.warning(
						f'Error restarting docker-compose file {compose_filename}, return code was {up_results_raw.returncode}'
					)


def process(args: argparse.Namespace):
	"""
	Main logic execution. Will load in all compose files from the given directory, stop the docker container if
	running, then back up any files that it can work out the location of, then restart the container again.

	:param args: Program arguments.
	"""

	compose_files = _get_compose_files()

	if not compose_files:
		logger.info('No docker compose commands found, nothing to do.')
		return

	config = toml.load(args.config)

	docker_compose_file_exclusions = config.get('docker_compose_exclusions', [])

	for compose_file in compose_files:
		if compose_file in docker_compose_file_exclusions:
			logger.info(f'Skipping compose file {compose_file}: excluded in config')
			continue

		_process_compose_file(compose_file, args, config)


def main():
	# Stop showing DEBUG messages from docker_composer_2
	base.logger.remove()
	base.logger.add(sys.stdout, level='INFO')

	argument_parser = argparse.ArgumentParser(
		description='Utility program to manage backups for docker-compose Docker containers'
	)

	argument_parser.add_argument(
		'-c',
		'--config',
		type=str,
		help='name of config file',
		default='config.toml',
		nargs='?',
		metavar='config filename',
	)

	argument_parser.add_argument(
		'-d',
		'--dry_run',
		help='perform a dry run',
		action='store_true',
	)

	argument_parser.add_argument(
		'-n',
		'--new_command',
		help='use the new style "docker compose" command instead of "docker-compose"',
		action='store_true',
	)

	args = argument_parser.parse_args()

	process(args)


if __name__ == '__main__':
	main()
