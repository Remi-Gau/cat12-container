"""Run CAT12 BIDS app."""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import nibabel as nb
from _parsers import common_parser
from _version import __version__
from bids_utils import (
    get_dataset_layout,
    init_derivatives_layout,
    list_subjects,
)
from cat_logging import cat12_log
from defaults import default_log_level
from rich import print
from rich_argparse import RichHelpFormatter
from utils import progress_bar

logger = cat12_log(name="cat12")

log_level_name = default_log_level()
logger.setLevel(log_level_name)

argv = sys.argv

with open(Path(__file__).parent / "exit_codes.json") as f:
    EXIT_CODES = json.load(f)

# Get environment variable
STANDALONE = Path(os.getenv("STANDALONE"))


def print_error_and_exit(message):
    """Log error and exit."""
    logger.error(message)
    #  print help
    subprocess.run([STANDALONE / "cat_standalone.sh"])
    sys.exit(EXIT_CODES["FAILURE"]["Value"])


def main():
    """Run the app."""
    parser = common_parser(formatter_class=RichHelpFormatter)

    args = parser.parse_args(argv[1:])

    output_dir = Path(args.output_dir[0])

    command = args.command

    if command == "copy":
        target = args.target[0]

        output_dir.mkdir(exist_ok=True, parents=True)

        if target == "all":
            files = STANDALONE.glob("*.m")
        else:
            files = [STANDALONE / f"cat_standalone_{target}.m"]

        for source_file in files:
            logger.info(f"Copying {source_file} to {str(output_dir)}")
            shutil.copy(source_file, output_dir)

        sys.exit(EXIT_CODES["SUCCESS"]["Value"])

    elif command == "view":
        target = args.target[0]
        source_file = STANDALONE / f"cat_standalone_{target}.m"
        with source_file.open("r") as file:
            print(f"[green]{file.read()}")

        sys.exit(EXIT_CODES["SUCCESS"]["Value"])

    bids_dir = Path(args.bids_dir[0])
    if not bids_dir.exists():
        logger.error(
            f"The following 'bids_dir' could not be found:\n{bids_dir}"
        )
        sys.exit(EXIT_CODES["DATAERR"]["Value"])

    layout_in = get_dataset_layout(bids_dir)

    output_dir = output_dir / f"CAT12_{__version__}"

    subjects = args.participant_label or layout_in.get_subjects()
    subjects = list_subjects(layout_in, subjects)

    analysis_level = args.analysis_level[0]
    if analysis_level == "group":
        logger.error("'group' level analysis not implemented yet.")
        sys.exit(EXIT_CODES["FAILURE"]["Value"])

    copy_files(layout_in, output_dir, subjects)

    layout_out = init_derivatives_layout(output_dir)

    text = "processing subjects"
    with progress_bar(text=text) as progress:
        subject_loop = progress.add_task(
            description="processing subjects", total=len(subjects)
        )
        for subject_label in subjects:
            this_filter = {}
            this_filter["datatype"] = "anat"
            this_filter["suffix"] = "T1w"
            this_filter["extension"] = "nii"
            this_filter["subject"] = subject_label

            bf = layout_out.get(
                **this_filter,
            )

            for file in bf:

                now = datetime.now().strftime("%s")
                log_file = (
                    output_dir
                    / f"sub-{subject_label}"
                    / "log"
                    / (now + "_" + Path(file.path).stem + ".log")
                )
                log_file.parent.mkdir(parents=True, exist_ok=True)

                with log_file.open("w") as log:
                    cmd = (
                        str(STANDALONE / "cat_standalone.sh ")
                        + file.path
                        + f" -b cat_standalone_{command}.m"
                    )
                    logger.info(cmd)

                    subprocess.run(
                        cmd.split(), stdout=log, stderr=subprocess.STDOUT
                    )

                progress.update(subject_loop, advance=1)

    sys.exit(EXIT_CODES["SUCCESS"]["Value"])


def copy_files(layout_in, output_dir, subjects):
    """Copy input files to derivatives.

    SPM has the bad habit of dumping derivatives with the raw.
    Unzip files as SPM cannot deal with gz files.
    """
    text = "copying subjects"
    with progress_bar(text=text) as progress:
        subject_loop = progress.add_task(
            description="copying subjects", total=len(subjects)
        )
        for subject_label in subjects:
            logger.info(f"Copying {subject_label}")

            this_filter = {
                "datatype": "anat",
                "suffix": "T1w",
                "extension": "nii.*",
                "subject": subject_label,
            }
            bf = layout_in.get(
                **this_filter,
                regex_search=True,
            )
            for file in bf:
                output_filename = output_dir / file.relpath
                if output_filename.suffix == ".gz":
                    output_filename = output_filename.with_suffix("")
                if output_filename.exists():
                    continue

                output_filename.parent.mkdir(exist_ok=True, parents=True)

                logger.info(f"Copying {file.path} to {str(output_dir)}")
                img = nb.load(file.path)
                nb.save(img, output_filename)

            progress.update(subject_loop, advance=1)


if __name__ == "__main__":
    main()
