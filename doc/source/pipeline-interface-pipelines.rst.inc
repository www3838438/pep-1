.. _pipeline-interface-pipelines:

Pipeline interface section: pipelines 
**************************************************

The ``pipelines`` section defines important information about each pipeline, including its name, script location on disk, and optional or required command-line arguments. In addition, if you're using a cluster resource manager, it also specifies which compute resources to request. For each pipeline, you specify values for a few specific keys. Let's start with a basic example:


.. code-block:: yaml

  pipelines:
    pipeline_key:  # this is variable (script filename)
      name: pipeline_name  # used for assessing pipeline flags (optional)
      path: relative/path/to/pipeline_script.py
      looper_args: True
      arguments:
        "-k" : value
        "--key2" : value
        "--key3" : null # value-less argument flags
      resources:
        default:
          file_size: "0"
          cores: "4"
          mem: "6000"
          time: "2-00:00:00"
        resource_package_name:
          file_size: "2"
          cores: "4"
          mem: "6000"
          time: "2-00:00:00"

Each pipeline gets its own section (here there's just one, ``pipeline_key``). The particular keys that you may specify for each pipeline are:

- ``name`` (recommended): Name of the pipeline. This is used to assess pipeline flags (if your pipeline employs them, like pypiper pipelines).
- ``path`` (required): Absolute or relative path to the script for this pipeline. Relative paths are considered **relative to your pipeline_interface file**. We strongly recommend using relative paths where possible to keep your pipeline interface file portable. You may also use shell environment variables (like ``${HOME}``) in the ``path``.
- ``arguments`` (required): List of key-value pairs of arguments required by the pipeline. The key corresponds verbatim to the string that will be passed on the command line to the pipeline, that is, the absolute, quoted name of the argument (like ``"--input"``). The value corresponds to an attribute of the sample, which will be derived from the sample_annotation csv file (in other words, it's a column name of your sample annotation sheet). Looper will find the value of this attribute for eash sample and pass that to the pipeline as the value for that argument. For flag-like arguments that lack a value, you may specify `null` as the value (e.g. `"--quiet-mode": null`). These arguments are considered **required**, and looper will not submit a pipeline if a sample lacks an attribute that is specified as a value for an argument.
- ``optional_arguments``: Any arguments listed in this section will be passed to the pipeline `if the specified attribute exists for the sample`. These are considered optional, and so the pipeline will still be submitted if they are not provided.
- ``required_input_files`` (optional): A list of sample attributes (annotation sheets column names) that will point to input files that must exist.
- ``all_input_files`` (optional): A list of sample attributes (annotation sheet column names) that will point to input files that are not required, but if they exist, should be counted in the total size calculation for requesting resources.
- ``ngs_input_files`` (optional): For pipelines using sequencing data, provide a list of sample attributes (annotation sheet column names) that will point to input files to be used for automatic detection of ``read_length`` and ``read_type`` sample attributes.

- ``looper_args`` (optional): Provide ``True`` or ``False`` to specify if this pipeline understands looper args, which are then automatically added for

  - ``-C``: config_file (the pipeline config file specified in the project config file; or the default config file, if it exists)
  - ``-P``: cores (the number of cores specified by the resource package chosen)
  - ``-M``: mem (the memory limit)

- ``resources`` (recommended): A section outlining how much memory, CPU, and clock time to request, modulated by input file size. If the ``resources`` section is missing, looper will only be able to run the pipeline locally (not submit it to a cluster resource manager). If you provide a ``resources`` section, you must define at least 1 option named 'default' with ``file_size: "0"``. Then, you define as many more resource "package" as you want. The ``resources`` section can be a bit confusing. Think of it like a group of steps of increasing size. The first step (default) starts at 0, and this step will catch any files that aren't big enough to get to the next level. Each successive step is larger. Looper determines the size of your input file, and then iterates over the resource packages until it can't go any further; that is, the ``file_size`` of the package is bigger (in gigabytes) than the input file size of the sample. At this point, iteration stops and looper has selected the best-fit resource package for that sample -- the smallest package that is still big enough. Add as many additional resource sets as you want, with any names. Looper will determine which resource package to use based on the ``file_size`` of the input file. It will select the lowest resource package whose ``file_size`` attribute does not exceed the size of the input file. Becuase the partition or queue name is relative to your environment, we don't usually specify this in the ``resources`` section, but rather, in the ``pepenv`` config. So, `file_size: "5"` means 5 GB. This means that resource package only will be used if the input files total size is greater than 5 GB.

Here is a more complete example that includes multiple pipelines:

.. code-block:: yaml

	pipelines:
	  rrbs:
	    name: RRBS
	    looper_args: True
	    path: path/to/rrbs.py
	    arguments:
	      "--sample-name": sample_name
	      "--genome": genome
	      "--input": data_path
	      "--single-or-paired": read_type
	    resources:
	      default:
	        file_size: "0"
	        cores: "4"
	        mem: "4000"
	        time: "2-00:00:00"
	      high:
	        file_size: "4"
	        cores: "6"
	        mem: "4000"
	        time: "2-00:00:00"

	  rnaBitSeq.py:
	    looper_args: True
	    arguments:
	      "--sample-name": sample_name
	      "--genome": transcriptome
	      "--input": data_path
	      "--single-or-paired": read_type
	    resources:
	      default:
	        file_size: "0"
	        cores: "6"
	        mem: "6000"
	        time: "2-00:00:00"

	  atacseq.py:
	    arguments:
	      "--sample-yaml": yaml_file
	      "-I": sample_name
	      "-G": genome
	    looper_args: True
	    resources:
	      default:
	        file_size: "0"
	        cores: "4"
	        mem: "8000"
	        time: "08:00:00"
