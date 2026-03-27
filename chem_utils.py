import requests, time, random, os, re

from rdkit import Chem
from rdkit.Chem import Descriptors
from rdkit.Chem import rdMolDescriptors
from rdkit.Chem import Lipinski

import pubchempy as pcp


def check_input(smi):

    smi = smi.strip()
    if '>>' in smi: #if reactionSMILES
        reactant, product = smi.split('>>')
        reactant = [canonicalize(x) for x in reactant.split('.')]
        product = [canonicalize(x) for x in product.split('.')]
        
        query_type = 'Reaction'
        compound_dict = {
            f"Reactant {i+1}": attribute_smi(x) for i, x in enumerate(reactant)
        } | {
            f"Product {i+1}": attribute_smi(x) for i, x in enumerate(product)
        }
    else: #if SMILES
        compound = [canonicalize(x) for x in smi.split('.')]
        
        query_type = 'Compound'
        compound_dict = {
            f"Compound {i+1}": attribute_smi(x) for i, x in enumerate(compound)
        }
    
    print('--- Input Reaction')
    for k, v in compound_dict.items():
        print(f"::: {k}: {v['IUPAC_Name']}")
        
    return compound_dict, query_type


def attribute_smi(smi: str) -> dict:
    smi = canonicalize(smi)
    mol = Chem.MolFromSmiles(smi)
    iupac_name = smi_to_iupac(smi)
    assert iupac_name is not None
    
    return attribute(mol, smi, iupac_name)


def attribute_iupac(iupac_name: str) -> dict:
    smi = iupac_to_smi(iupac_name)
    assert smi is not None
    
    smi = canonicalize(smi)
    mol = Chem.MolFromSmiles(smi)
    iupac_name = smi_to_iupac(smi)
    assert iupac_name is not None

    return attribute(mol, smi, iupac_name)


def attribute(mol, smi: str, iupac_name: str, decimal = 2):

    halogens = ["F", "Cl", "Br", "I"]
    pats = {
        "-OH":  Chem.MolFromSmarts("[#8;H1]"),
        "-NH2": Chem.MolFromSmarts("[#7;H2]"),
        "-NH":  Chem.MolFromSmarts("[#7;H1]")
    }

    _dict = {
        'SMILES': smi,
        'IUPAC_Name': iupac_name,
        'Mol_Formula': rdMolDescriptors.CalcMolFormula(mol),
        'Exact_Mass': round(Descriptors.ExactMolWt(mol),  decimal),
        'LogP': round(Descriptors.MolLogP(mol),  decimal),
        'TPSA': round(Descriptors.TPSA(mol),  decimal),
        'HBA_Count': Lipinski.NumHAcceptors(mol),
        'HBD_Count': Lipinski.NumHDonors(mol),
        'Aromatic_Ring_Count': rdMolDescriptors.CalcNumAromaticRings(mol),
        'Halogen_Count': ", ".join(f"{h} ({sum(a.GetSymbol()==h for a in mol.GetAtoms())})" for h in halogens),# if any(a.GetSymbol()==h for a in mol.GetAtoms())
        'Functional_Group_Count': ", ".join(f"{k} ({len(mol.GetSubstructMatches(v))})" for k, v in pats.items())# if mol.HasSubstructMatch(v)
    }

    return _dict
    

def smi_to_iupac(smiles: str) -> str:
    for fn in (cactus_smi_to_iupac, pubchem_smi_to_iupac):
        try:
            return fn(smiles)
        except:
            continue
    return None


def iupac_to_smi(iupac_name: str) -> str:
    for fn in (cactus_iupac_to_smi, pubchem_iupac_to_smi):
        try:
            return fn(iupac_name)
        except:
            continue
    return None


def cactus_smi_to_iupac(smiles: str) -> str:
    smiles = smiles.replace('#','%23')
    url = 'https://cactus.nci.nih.gov/chemical/structure/%s/iupac_name'%smiles
    response = requests.get(url)
    response.raise_for_status()
    assert len(response.text) < 100 and len(response.text) > 0
    return response.text


def pubchem_smi_to_iupac(smiles: str) -> str:
    match = pcp.get_compounds(smiles, namespace='smiles')[0]
    assert match.iupac_name is not None
    return match.iupac_name


def cactus_iupac_to_smi(iupac_name: str) -> str:
    iupac_name = iupac_name.replace(' ','%20')
    url = 'https://cactus.nci.nih.gov/chemical/structure/%s/smiles'%iupac_name
    response = requests.get(url)
    response.raise_for_status()
    assert len(response.text) < 100 and len(response.text) > 0
    return response.text


def pubchem_iupac_to_smi(iupac_name: str) -> str:
    match = pcp.get_compounds(iupac_name, namespace='name')[0]
    assert match.canonical_smiles is not None
    return match.canonical_smiles


def canonicalize(smi: str) -> str:
    return Chem.MolToSmiles(Chem.MolFromSmiles(smi))