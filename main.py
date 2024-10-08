import argparse
import collections.abc
import contextlib
import json
import os
import re
import shutil
import sys
import tarfile

import more_itertools
import toml
import yaml
from docker_composer_v2 import DockerCompose, base
from loguru import logger

from compose_model import ComposeSpecification

logger = logger.patch(lambda record: record.update(name='docker-composer-backer-upper'))


def _get_compose_files() -> collections.abc.Iterable[str]:
	"""
	Determine list of compose files to process.

	:return: List of filenames found in the directory ending in .yml.
	"""

	docker_compose_instance = DockerCompose()

	ls_results_raw = docker_compose_instance.ls(all=True, format='json').call(capture_output=True)

	ls_results = json.loads(ls_results_raw.stdout)

	return more_itertools.collapse(
		[
			result['ConfigFiles'].split(',')
			for result in ls_results
			if result['Status'].startswith('running')
		]
	)


def _get_compose_model(compose_filename: str) -> ComposeSpecification:
	"""
	For a given compose filename, attempt to build a docker-compose Model object from it.

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

	number_of_backups = config.get('num_backups', 2)
	is_dry_run = args.dry_run

	if not is_dry_run:
		for backup_counter in range(number_of_backups, -1, -1):
			if backup_counter:
				potential_backup_folder = f'{target_backup_file}.{backup_counter}'
			else:
				potential_backup_folder = target_backup_file

			if os.path.exists(potential_backup_folder):
				# If it's the last one, nuke it
				if backup_counter == number_of_backups:
					shutil.rmtree(potential_backup_folder)
				else:
					shutil.move(
						potential_backup_folder, f'{target_backup_file}.{backup_counter + 1}'
					)

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

						target_file_context.add(volume)
				except Exception as e:
					logger.error(f'Error copying files: {e}')


def _process_compose_file(compose_filename: str, args: argparse.Namespace, config: dict):
	compose_model = _get_compose_model(compose_filename)

	volumes_to_backup = {}

	exclusions = set(config.get('volume_exclusions', []))
	inclusions = set(config.get('volume_inclusions', []))

	for service_name, service in compose_model.services.items():
		compose_file_volumes = set()

		for volume in service.volumes or []:
			if volume.startswith('/'):
				volume = volume.split(':')[0]

				# First, look for forced inclusions
				inclusion_found = False

				for inclusion in inclusions:
					inclusion_re = re.compile(inclusion)

					if inclusion_re.match(volume):
						inclusion_found = True
						break

				if inclusion_found:
					compose_file_volumes.add(volume)
					continue

				# Otherwise, check and see if we have to exclude the volume instead.
				exclusion_found = False

				for exclusion in exclusions:
					exclusion_re = re.compile(exclusion)

					if exclusion_re.match(volume):
						exclusion_found = True
						break

				if not exclusion_found:
					compose_file_volumes.add(volume)

		if compose_file_volumes:
			volumes_to_backup[service.container_name or service_name] = compose_file_volumes

	if volumes_to_backup:
		docker_compose_instance = DockerCompose(file=compose_filename)

		docker_stopped = False

		try:
			if args.dry_run:
				logger.info(f'Would have stopped docker-compose file {compose_filename}')
			else:
				down_results_raw = docker_compose_instance.down().call(capture_output=True)

				docker_stopped = down_results_raw.returncode == 0

			for service_name, volumes in volumes_to_backup.items():
				_backup_volumes(args, config, service_name, volumes)
		except:
			logger.exception(f'Attempting to bring down {compose_filename} and copy volumes')
		finally:
			if docker_stopped:
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

	config = toml.load(args.config)

	docker_compose_file_exclusions = config.get('docker_compose_exclusions', [])

	for compose_file in filter(
		lambda filename: filename not in docker_compose_file_exclusions, compose_files
	):
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
	args = argument_parser.parse_args()

	process(args)


if __name__ == '__main__':
	main()
