import argparse
import json
import logging
import os
import shutil
from collections.abc import Iterable

import more_itertools
import toml
import yaml
from docker_composer_v2 import DockerCompose

from compose_model import ComposeSpecification

logger = logging.getLogger(__name__)


def _get_compose_files() -> Iterable[str]:
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


def _backup_volume(args: argparse.Namespace, service_name: str, volume: str):
	target_backup_folder = os.path.join(args.destination, service_name)

	for backup_counter in range(args.num_backups, -1, -1):
		if backup_counter:
			potential_backup_folder = f'{target_backup_folder}.{backup_counter}'
		else:
			potential_backup_folder = target_backup_folder

		if os.path.exists(potential_backup_folder):
			# If it's the last one, nuke it
			if backup_counter == args.num_backups:
				shutil.rmtree(potential_backup_folder)
			else:
				shutil.move(potential_backup_folder, f'{target_backup_folder}.{backup_counter + 1}')

	shutil.copytree(volume, os.path.join(target_backup_folder, volume[1:]))


def _process_compose_file(args: argparse.Namespace, compose_filename: str, exclusions: set[str]):
	compose_model = _get_compose_model(compose_filename)

	for service_name, service in compose_model.services.items():
		compose_file_volumes = set()

		for volume in service.volumes or []:
			if volume.startswith('/'):
				volume = volume.split(':')[0]

				exclusion_found = False

				for exclusion in exclusions:
					if volume.startswith(exclusion):
						exclusion_found = True
						break

				if not exclusion_found:
					compose_file_volumes.add(volume)

		if compose_file_volumes:
			docker_compose_instance = DockerCompose(file=compose_filename)

			docker_stopped = False

			try:
				down_results_raw = docker_compose_instance.down().call(capture_output=True)

				docker_stopped = down_results_raw.returncode == 0

				for volume in compose_file_volumes:
					_backup_volume(args, service.container_name or service_name, volume)
			except:
				logger.exception(f'Attempting to bring down {compose_filename}')
			finally:
				if docker_stopped:
					up_results_raw = docker_compose_instance.up(detach=True).call(
						capture_output=True
					)

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

	exclusions = []

	if args.exclusions:
		try:
			exclusions_file = toml.load(args.exclusions)

			if 'exclusions' not in exclusions_file:
				logger.info(f'No exclusions entry found in {args.exclusions}')
			else:
				exclusions = set(exclusions_file['exclusions'])
		except:
			logger.exception('Loading exclusions from TOML file')

	for compose_file in compose_files:
		_process_compose_file(args, compose_file, exclusions)


def main():
	argument_parser = argparse.ArgumentParser(
		description='Utility program to manage backups for docker-compose Docker containers'
	)
	argument_parser.add_argument(
		'destination', type=str, help='directory to place backups of container files in'
	)

	argument_parser.add_argument(
		'-n',
		'--num_backups',
		type=int,
		help='number of backups to keep for each compose file',
		default=5,
		nargs='?',
		metavar='number',
	)

	argument_parser.add_argument(
		'-e',
		'--exclusions',
		type=str,
		help='name of volume exclusions TOML file',
		default='exclusions.toml',
		nargs='?',
		metavar='exclusions filename',
	)

	args = argument_parser.parse_args()

	process(args)


if __name__ == '__main__':
	main()
