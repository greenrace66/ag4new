"""
This script contains the class ODDT_IFP that rescores Vina type docking
by comparing each pose interaction fingerprint with a given reference 
compound (crystal reference) exploiting the fingerprint module of the 
Open Drug Discovery Toolkit Python library
"""
import __future__

import glob
import os
import sys


from autogrow.docking.scoring.scoring_classes.parent_scoring_class import ParentScoring
from autogrow.docking.scoring.scoring_classes.scoring_functions.vina import VINA

#### additional import
import numpy as np
import oddt
from oddt import fingerprints
import sklearn.metrics
from sklearn.metrics import pairwise_distances
from operator import itemgetter
from collections import OrderedDict

#np.set_printoptions(threshold=sys.maxsize)


class ODDT_IFP(VINA):
    """
    This will Score a given ligand for its binding affinity based on VINA or
    QuickVina02 type docking.

    Inputs:
    :param class ParentFilter: a parent class to initialize off of.
    """

    def __init__(self, vars=None, smiles_dict=None, test_boot=True):
        """
        This will take vars and a list of smiles.

        Inputs:
        :param dict vars: Dictionary of User variables
        :param dict smiles_dict: a dict of ligand info of SMILES, IDS, and
            short ID
        :param bool test_boot: used to initialize class without objects for
            testing purpose
        """

        if test_boot is False:
            self.vars = vars

            self.smiles_dict = smiles_dict
            print("")
            print("######################")
            print("Running ODDT_IFP rescoring on vina files")


    #######################
    # Executed by the Execute_Scoring.py script
    #######################
    def find_files_to_score(self, file_path):
        """
        Find all files of the appropriate file format within the dir. For this
        class its .pdbqt.vina files.

        ALL SCORING FUNCTIONS MUST HAVE THIS FUNCTION.

        Inputs:
        :param str file_path: the path to the file to be scored

        Returns:
        :returns: list list_of_ODDT_IFP_files: list of all files to be scored
            within the dir
        """

        self.file_path = file_path

        list_of_docked_files = []

        list_of_docked_files = glob.glob(file_path + "*.pdbqt.vina")

        return list_of_docked_files

    def run_rescoring(self, vina_output_file):
        """
        Run the ODDT_IFP scoring on all of these files. Return a list of a rescored
        file with ODDT_IFP ie *.pdbqt.vina.oddt_ifp

        Inputs:
        :param str vina_output_file: Path to a vina output file to be rescored

        Returns:
        :returns: list results of the rescoring function: [file_path,
            it_rescored]. [PATH, True] means it passed. [PATH, False] means it
            failed a results of all ODDT_IFP files.
        """
        #### outside of class for multithreading
        result_of_rescore = run_oddt_ifp_rescoring(self.vars, vina_output_file)

        return result_of_rescore

    def run_scoring(self, file_path):
        """
        Get all relevant scoring info and return as a list

        This is required for all Scoring Functions. Additional manipulations
        may go here but there are none for this script..

        Inputs:
        :param str file_path: the path to the file to be scored

        Returns:
        :returns: list list_of_lig_data: information about the scored ligand.
            Score is last index (ie. [lig_id_shortname, any_details,
            fitness_score_to_use] )
        """

        if os.path.exists(file_path):
            lig_info = self.get_score_from_a_file(file_path)
            return lig_info

        # file_path does not exist
        return None

    def get_score_from_a_file(self, file_path):
        """
        Make a list of a ligands information including its docking score.

        Because a higher score is better for ODDT_IFP scoring function (0 to 1), 
        but AutoGrow4 selects based on most negative score, we multiple each 
        ODDT_IFP score value by -1.0. This ensures that the best score is the 
        most negative score.

        Inputs:
        :param str file_path: the path to the file to be scored

        Returns:
        :returns: list lig_info: a list of the ligands short_id_name and the
            docking score from the best pose.
        """

        if ".oddt_ifp" not in file_path:
            if ".vina" in file_path:
                file_path = file_path + ".oddt_ifp"
                if os.path.exists(file_path) is False:
                    return None
            else:
                return None
        if os.path.exists(file_path) is False:
            return None
        # grab the index of the ligand for the score
        basefile = os.path.basename(file_path)
        ligand_pose = basefile.split(".pdbqt.vina.oddt_ifp")[0]
        basefile_split = basefile.split("__")
        ligand_short_name = basefile_split[0]

        score = None

        with open(file_path, "r") as f:
            for line in f.readlines():

                if "The best score is: " in line:
                    try:
                        tmp = line.split(": ")
                        temp_score = float(tmp[1].rstrip('\n'))
                    except:
                        continue
                    if score is None:
                        score = temp_score

        if score is None:
            # This file lacks a pose to use
            return None

        lig_info = [ligand_short_name, ligand_pose, score]

        # Obtain additional file info
        lig_info = self.merge_smile_info_w_affinity_info(lig_info)    #inherited from VINA

        if lig_info is None:
            return None
        lig_info = [str(x) for x in lig_info]

        return lig_info


###Outside class for multithreading
# Run ODDT_IFP rescoring
def run_oddt_ifp_rescoring(vars, vina_output_file):
    """
    This will run ODDT_IFP on all of the vina files in the list. This is outside
    the class for multifunction purposes

    Returns A list containing the file name as item 1 and whether it passed as
    item 2. [PATH, True] means it passed. [PATH, False] means it failed a
    results of all ODDT_IFP files.

    Inputs:
    :param dict vars: User variables which will govern how the programs runs
    :param str vina_output_file: Path to a vina output file to be rescored

    Returns:
    :returns: list results of the rescoring function: [file_path,
        it_rescored]. [PATH, True] means it passed. [PATH, False] means it failed
        a results of all ODDT_IFP files.
    """

    if vina_output_file is None:
        return None
    # Unpackage vars
    receptor = vars["filename_of_receptor"]
    try:
        ref = vars["reference_ligand"]
    except:
        raise NotImplementedError(
            "reference_ligand can not be found. \
            File must be a .pdbqt file."
        )
    oddt_ifp_output = vina_output_file + ".oddt_ifp"

    # A list containing the file name as item 1 and whether it passed as item
    # 2
    results = execute_oddt_ifp_scoring(vars, receptor, ref, vina_output_file, oddt_ifp_output)

    # Will be None if it passed. A list containing the file name as item 1 and
    # whether it passed as item 2. [PATH, True] means it passed. [PATH, False]
    # means it failed.
    return results


def execute_oddt_ifp_scoring(vars, receptor, ref, vina_output_file, file_path):
    """
    Run an individual ODDT_IFP scoring function.

    returns A list containing the file name as item 1 and whether it passed as
    item 2. [PATH, True] means it passed. [PATH, False] means it failed.

    Inputs:
    :param str command: the rescoring bash style command to execute
    :param str file_path: Path to a vina output file to be rescored

    Returns:
    :returns: list results of the rescoring function: [file_path,
        it_rescored]. [PATH, True] means it passed. [PATH, False] means it failed
        a results of all ODDT_IFP files.
    """

    try:
        prot = receptor + "qt"
        basename = os.path.basename(vina_output_file)
        ref_extension = os.path.basename(ref).split('.')[1]
        protein = next(oddt.toolkit.readfile('pdbqt', prot))
        protein.protein = True
        reference = next(oddt.toolkit.readfile(ref_extension, ref))
        ref_fp = fingerprints.InteractionFingerprint(reference, protein)
        sim_dict = {}
        best_score = 0
        top_pose = 0
        count = 0
        for ligand in oddt.toolkit.readfile('pdbqt', vina_output_file, lazy=True):
            fp = fingerprints.InteractionFingerprint(ligand, protein)
            l_plif_temp=[]
            l_plif_temp.append(ref_fp)
            l_plif_temp.append(fp)
            matrix=np.stack(l_plif_temp, axis=0)
            idx = np.argwhere(np.all(matrix[..., :] == 0, axis=0))
            matrix_dense = np.delete(matrix, idx, axis=1)
            x=matrix_dense[0].reshape(1,-1)
            y=matrix_dense[1].reshape(1,-1)
            sim_giovanni=float(sklearn.metrics.pairwise.cosine_similarity(x, y))
            sim_dict[count] = round(sim_giovanni * -1,2)
            count += 1
        sorted_sim_dict = OrderedDict(sorted(sim_dict.items(), key=itemgetter(1)))
        best_score = list(sorted_sim_dict.items())[0][1]
        top_pose = list(sorted_sim_dict.items())[0][0]
        with open(file_path,'w') as f:
            output = '''Molecule: %s
The best pose is: pose %d
The best score is: %.2f
''' %(basename,top_pose,best_score)
            f.write(output)
        it_rescored = confirm_file_has_scoring(file_path)
    except:
        return [file_path, False]
    return [file_path, it_rescored]


def confirm_file_has_scoring(file_path):
    """
    Check the file has a rescore value

    Inputs:
    :param str file_path: Path to a vina output file to be rescored
    Returns:
    :returns: bol has_scoring: True if has score;
        False if no score found
    """

    if os.path.exists(file_path) is False:
        return False
    with open(file_path, "r") as f:
        has_scoring = False
        for line in f.readlines():

            if "The best score is:" in line:
                has_scoring = True
                return has_scoring
    return has_scoring
