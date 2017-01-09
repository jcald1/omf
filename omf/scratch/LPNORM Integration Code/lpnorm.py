''' Perform a resilience analysis on a circuit using LANL's Fragility and RDT. '''

import sys, os, sys, json
from os.path import join as pJoin
from matplotlib import pyplot as plt
import subprocess, random, webbrowser
import pprint as pprint

# OMF imports
import omf.feeder as feeder
from omf.solvers import gridlabd


# Functions.
def createObj(objToRet):
	'''Creates rdt input file objects.
	'''
	if objToRet=='scenario':
		# scenario: an rdt input has multiple unique scenarios.
		# required: id.		
		scenarioObj = {
			'id' : "1", #*
			'disable_line' : [],
			'hardened_disabled_lines' : []
		}
		return scenarioObj
	elif objToRet=='line_code':	
		# line_code: impedenance and resistance values of lines, may be unique for each line.
		# required: all.
		# TODO: read and give transformer specific line codes to transformer lines.
		line_codeObj = {
			'line_code': '', #*
			'num_phases': '', #*
			'xmatrix': [[],[],[]], #* reactance terms: phaseA, phaseB, and phaseC.
			'rmatrix': [[],[],[]] #* resistance terms: phaseA/B/C.
		}
		return line_codeObj
	elif objToRet=='line':
		# lines: a line in the model. 
		# required: id, node1, node2, length, line_code, num_phases, has_phase, harden_cost: 1.
		lineObj = {
			'id' : '', #*
			'node1_id' : '', #*
			'node2_id' : '', #*
			'line_code' : '', #*
			'length' : 1.0, #* Units match line code entries.
			# 'has_switch' : False,
			# 'construction_cost': 100,
			'harden_cost': 100000, # Russel: this exists unless its a trans.
			# 'switch_cost': 15, # taken from rdtInTrevor.json.
			# 'can_harden': False, # Not seen in rdtInTrevor.json.
			# 'can_add_switch': False, # Not seen in rdtInTrevor.json.
			# 'num_poles' : 2,
			# 'capacity' : 5780, # MVA capacity.
			# 'is_transformer' : False,
			'num_phases' : 3, #*
			# 'is_new' : False,
			'has_phase' : [True, True, True] #*
		}
		return lineObj
	elif objToRet=='bus':
		# bus: node data.
		# req: id.
		busObj = {
			'id': '', #*
			# 'min_voltage': 0.8, # in p.u.
			# 'max_voltage': 1.2, # in p.u.
			# 'y': '', # not in schema.
			# 'x': '', # not in schema.
			# 'has_generator': False,
			# 'has_phase': [True, True, True],
			# 'ref_voltage': [1.0, 1.0, 1.0]
			# 'ref_voltage': 1.0 # From github.
		}
		return busObj
	elif objToRet=='load':
		# load: load data.
		# req: id, node_id, max_real_phase, max_reac_phase, has_phase.
		loadObj = {
			'id': '', #*
			'node_id': '', #*
			'is_critical': False, 
			'max_real_phase': [], #*
			'max_reactive_phase': [], #*
			'has_phase': [] #*
		}
		return loadObj
	elif objToRet=='gen':
		# generator: generator data.
		# req: id, node_id, has_phase, max_reac_phase, max_real_phase.
		genObj = {
			'id': '', #*
			'node_id': '', #*
			# 'is_new': False, # Whether or not new generation can be built.
			# 'microgrid_cost': 1.5, # Per MW capacity of building DG.
			# 'max_microgrid': 0, # Max additional capacity for this gen.
			# 'microgrid_fixed_cost': 0, # One-time fixed cost for building DG.
			'has_phase': [True, True, True], #*
			'max_reactive_phase': [1.7976931348623e+308, 1.7976931348623e+308, 1.7976931348623e+308], #*
			'max_real_phase': [1.7976931348623e+308, 1.7976931348623e+308, 1.7976931348623e+308] #*
		}		
		return genObj
	else:
		# Incorrectly entered object.
		print "The object: %s doesn't exist."%(str(objToRet))
		return {}

def getNodePhases(obj, defReal=1.7976931348623e+308, defReact=1.7976931348623e+308):
	'''read omd., 10json obj's phases and convert to rdt format.
	'''
	numPhases = 0
	hasphaseA, hasphaseB, hasphaseC = False, False, False
	maxRealPhaseA, maxRealPhaseB, maxRealPhaseC = 0, 0, 0
	maxReactivePhaseA, maxReactivePhaseB, maxReactivePhaseC = 0, 0, 0
	phases = obj.get('phases','').strip('S').strip('N')
	if phases != '': 
		if 'A' in phases: 
			hasphaseA = True
			maxRealPhaseA = defReal
			maxReactivePhaseA = defReact
			numPhases+=1
		if 'B' in phases: 
			hasphaseB = True
			maxRealPhaseB = defReal
			maxReactivePhaseB = defReact
			numPhases+=1
		if 'C' in phases: 
			hasphaseC = True
			maxRealPhaseC = defReal
			maxReactivePhaseC = defReact
			numPhases+=1
	else:
		print "NO PHASES FOUND FOR OBJ:", obj	
	return numPhases, [hasphaseA, hasphaseB, hasphaseC], [maxRealPhaseA, maxRealPhaseB, maxRealPhaseC], [maxReactivePhaseA, maxReactivePhaseB, maxReactivePhaseC]

def makeScenarios(rdtJson, jsonTree, debug):
	'''puts in damage scenario from fragility.  
	'''
	if debug: 
		print "Created %s scenarios"%(str(len(rdtJson['scenarios'])))
		if debug==2:
			for elem in rdtJson['scenarios']: 
				print "   Scenario:"
				for a,val in elem.iteritems():
					print "      %s: %s"%(str(a), str(val))	
def makeLines(rdtJson, jsonTree, debug):
	''' lines.
	TODO: Put in accurate num_poles, ask if has_phase corresponds to a,b,c.
	TODO: Insert harden_cost calc.
	'''
	objToFind, lineCount = ['triplex_line','transformer', 'regulator'], 0
	for key, line in jsonTree.iteritems():
		if line.get('object','') in objToFind:
			newLine = createObj('line')
			newLine['id'], newLine['node1_id'], newLine['node2_id'], newLine['length'], newLine['line_code'] = \
				line.get('name',''), line.get('from','')+'_bus', line.get('to','')+'_bus', float(line.get('length',100))/100, lineCount
			newLine['num_phases'], newLine['has_phase'], maxRealPhase, maxReactivePhase = getNodePhases(line)
			# Calculate harden_cost, 10.
			# newLine['capacity'] = 1000000000 # Set it arbitrarily high.
			if line.get('object','') == 'transformer': 
				newLine['is_transformer'] = True
				newLine.pop('harden_cost',None)
 			rdtJson['lines'].append(newLine)
			# print "Added newLine: %s (TOTAL: %s)\n"%(newLine, str(lineCount+1))
			lineCount+=1
	if debug: 
		print "Created %s lines"%(str(len(rdtJson['lines'])))
		if debug==2:
			for elem in rdtJson['lines']: 
				print "   Line:"
				for a,val in elem.iteritems():
					print "      %s: %s"%(str(a), str(val))				
	return lineCount
def makeLineCodes(rdtJson, jsonTree, lineCount, inDir, debug):
	'''line_codes: create one for each line.
	For now, use values from rdtInputTrevor.json.
	TODO*: keep track of which matrices have 0 for which phases, and use appropriate ones.
	TODO: Give special x/r matrices for transformers.
	TODO: Read x/r matrices from gridlabD csv recorder file.
	'''
	xMatrices, rMatrices = readXRMatrices(inDir, 'rdtInSimple_Market_System.json', 100)
	for lineCode in range(0,lineCount):
		newLineCode = createObj('line_code')
		newLineCode['line_code'] = lineCode
		# Get phases and which phase a/b/c exists.
		newLineCode['num_phases'] = rdtJson['lines'][lineCode]['num_phases']
		if int(newLineCode['num_phases']) < 3: 
			phasesExist = rdtJson['lines'][lineCode]['has_phase']
		if int(newLineCode['num_phases']) == 3: 	
			# Set right x/r matrices for 3 phase.
			newLineCode['xmatrix'] = xMatrices[3][0]
			newLineCode['rmatrix'] = rMatrices[3][0]
			if len(xMatrices[3])>1: xMatrices[3].pop(0)
			if len(rMatrices[3])>1: rMatrices[3].pop(0)
		elif int(newLineCode['num_phases']) == 2: 
			# Set it for 2 phase.
			xMatrix = [[0.26732955, 0.12200757999999999, 0.0], [0.12200757999999999, 0.27047349, 0.0], [0.0, 0.0, 0.0]]
			rMatrix = [[0.36553030, 0.04407197, 0.0], [0.04407197, 0.36282197, 0.0], [0.0, 0.0, 0.0]]
			newLineCode['xmatrix'] = xMatrix
			newLineCode['rmatrix'] = rMatrix				
			print "      ****THIS LINECODE:\n      %s\n      ISNT TESTED FOR THIS OBJECT:\n      %s\n      NEED A 2 PHASE LINE FEEDER."%(rdtJson['lines'][lineCode], newLineCode)
		else:
			# Set it for 1 phase.
			xMatrix = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
			rMatrix = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
			for i,exists in enumerate(phasesExist):
				if exists:
					# Set xmatrix.
					for xSubMatrix in xMatrices[1][0]:
						for val in xSubMatrix:
							if float(val) != 0.0: 
								xMatrix[0][i] = val
								break
					# Set rmatrix.
					for rSubMatrix in rMatrices[1][0]:
						for val in rSubMatrix:
							if float(val) != 0.0: 
								rMatrix[0][i] = val
								break
			newLineCode['xmatrix'] = xMatrix
			newLineCode['rmatrix'] = rMatrix									
		rdtJson['line_codes'].append(newLineCode)
	if debug==True:
		print "Created %s line_codes"%(str(len(rdtJson['line_codes'])))
		if debug==2:
			for elem in rdtJson['line_codes']: 
				print "   Line_Code:"
				for a,val in elem.iteritems():
					print "      %s: %s"%(str(a), str(val))				 
def makeBuses(rdtJson, jsonTree, debug):
	'''buses.
	Ziploads? house? regulator? Waterheater?
	'''
	objToFind = ['node', 'triplex_node', 'triplex_meter']
	for key, bus in jsonTree.iteritems():
		# if bus.get('object','') in objToFind and bus.get('bustype','').lower() != 'swing':
		if bus.get('object','').lower() in objToFind:
			newBus = createObj('bus')
			newBus['id'] = bus.get('name','')+'_bus'
			if bus.get('bustype','').lower() == 'swing':
				newBus['has_generator'] = True
			numPhases, newBus['has_phase'], max_real_phase, max_reactive_phase = getNodePhases(bus)
			# Remove entries I couldn't find, 10.
			# newBus.pop('y',None)
			# newBus.pop('x',None)
			rdtJson['buses'].append(newBus)
			# newBus.pop('ref_voltage', None)
			# newBus.pop('min_voltage', None)
			# newBus.pop('max_voltage', None)
	if debug: 
		print "Created %s buses"%(str(len(rdtJson['buses'])))
		if debug==2:
			for elem in rdtJson['buses']: 
				print "   Bus:"
				for a,val in elem.iteritems():
					print "      %s: %s"%(str(a), str(val))					
def makeLoads(rdtJson, jsonTree, debug):
	'''loads.
	TODO*: How do I calculate real_phase and reactive_phase?
	'''
	objToFind = ['triplex_meter']
	for key, loads in jsonTree.iteritems():
		if loads.get('object','') in objToFind:
			newLoad = createObj('load')
			newLoad['id'] = loads.get('name','')+'_lod'
			for elem in rdtJson['buses']:
				if elem['id'][0:-4] == newLoad['id'][0:-4]:
					busID = elem['id']
					if debug==2: 
						print "      **Found load: %s bus as: %s**"%(newLoad['id'], busID)
			newLoad['node_id'] = busID
			numPhases, newLoad['has_phase'], newLoad['max_real_phase'], newLoad['max_reactive_phase'] = getNodePhases(loads, 10, 10)
			# newLoad.pop('is_critical',None)
			rdtJson['loads'].append(newLoad)
	if debug: 
		print "Created %s loads"%(str(len(rdtJson['loads'])))
		if debug==2:
			for elem in rdtJson['loads']: 
				print "   Load:"
				for a,val in elem.iteritems():
					print "      %s: %s"%(str(a), str(val))				
def makeGens(rdtJson, jsonTree, debug):
	'''generators.
	'''
	for key, gens in jsonTree.iteritems():
		if gens.get('bustype','').lower() == 'swing':
			newGen = createObj('gen')
			newGen['id'] = gens.get('name','')+'_gen'
			for elem in rdtJson['buses']:
				if elem['id'][0:-4] == newGen['id'][0:-4]:
					busID = elem['id']
					if debug: 
						print "   **Found Generator: %s\n With bus  %s**"%(newGen['id'], busID)
			newGen['node_id'] = busID	
			numPhases, newGen['has_phase'], newGen['max_real_phase'], newGen['max_reactive_phase'] = getNodePhases(gens)
			rdtJson['generators'].append(newGen)
	if debug: 
		print "Created %s generators"%(str(len(rdtJson['generators'])))
		if debug==2:
			for elem in rdtJson['generators']: 
				print "   Generator:"
				for a,val in elem.iteritems():
					print "      %s: %s"%(str(a), str(val))				
def convertToRDT(inData, inDir, feederName, debug=False):
	'''Read a omd.json feeder and convert it to fragility/RDT format.
	'''
	# Create RDT dict.
	if debug:
		print "Generating RDT input..."
		print "************************************"
	rdtJson = {
		'phase_variation' : inData.get('phase_variation', 0.15), 
		'chance_constraint' : inData.get('chance_constraint', 1.0),
		'critical_load_met' : inData.get('critical_load_met',0.98),
		'total_load_met' : inData.get('total_load_met',0.5),
		'scenarios' : [createObj('scenario')], # Made up fragility damage scenario.
		'line_codes' : [],
		'lines' : [],
		'buses' : [],
		'loads' : [],
		'generators' : []	
	}
	# Read and put omd.json into rdt.json.
	with open(pJoin(inDir,feederName), "r") as jsonIn:
		jsonTree = json.load(jsonIn).get('tree','')
	makeScenarios(rdtJson, jsonTree, debug)
	lineCount = makeLines(rdtJson, jsonTree, debug)
	makeLineCodes(rdtJson, jsonTree, lineCount, inDir, debug)
	makeBuses(rdtJson, jsonTree, debug)
	makeLoads(rdtJson, jsonTree, debug)
	makeGens(rdtJson, jsonTree, debug)
	# Write to file.
	rdtInFile = 'rdtIn'+feederName.strip('omd')+'json'
	with open(pJoin(inDir,rdtInFile), "w") as outFile:
		json.dump(rdtJson, outFile, indent=4)
	if debug:		
		print "Done... RDT input saved to:            %s"%(pJoin(inDir,rdtInFile))
		print "************************************\n\n"
	return rdtInFile

def convertToFrag(inData, inDir, feederName, debug=False):
	# Read and put rdtJson into frag.json.
	if debug:
		print "Generating fragility input..."
		print "************************************"
	rdtInFile = 'rdtIn'+feederName.strip('omd')+'json'
	with open(pJoin(inDir,rdtInFile), "r") as jsonIn:
		fragJson = json.load(jsonIn).get('scenarios','')
	fragInFile = 'fragIn'+feederName.strip('omd')+'json'
	with open(pJoin(inDir,fragInFile), "w") as outFile:
		json.dump(fragJson, outFile, indent=4)	
	if debug:	
		print "Done... Fragility input saved to:      %s"%(pJoin(inDir,fragInFile))
		print "************************************\n\n"
	return fragInFile


def readXRMatrices(inDir, rdtFile, length):
	'''Read XR Matrices from rdtFile. Add gridlabD csv file reading later.
	'''
	xMatrix, rMatrix = {1: [], 2: [], 3: []}, {1: [], 2: [], 3: []}
	with open(pJoin(inDir,rdtFile), "r") as jsonIn:
		lineCodes = json.load(jsonIn)['line_codes']
	for i,code in enumerate(lineCodes):
		if i > length: break
		xMatrix[int(code['num_phases'])].append(code['xmatrix'])
		rMatrix[int(code['num_phases'])].append(code['rmatrix'])
	return xMatrix, rMatrix

def setFragInputFiles(inDir, fragInFile, disasterFiles):
	'''Read input json, correct weather data file paths.
	'''
	with open(pJoin(inDir,fragInFile), "r") as jsonIn:
		fragContents = json.load(jsonIn)
	for key in fragContents.keys():
		if key == 'hazardFields':
			for hazardDict in fragContents[key]:
				for hazkey in hazardDict.keys():
					if hazkey == 'rasterFieldData':
						if hazardDict[hazkey].get('uri','') != '':
							if hazardDict.get('hazardQuantityType','') in disasterFiles.keys():
								fileName = disasterFiles[hazardDict.get('hazardQuantityType','')]
								hazardDict[hazkey]['uri'] = 'file:///'+pJoin(inDir,fileName)
	with open(pJoin(inDir,fragInFile), "w") as outFile:
		json.dump(fragContents, outFile, indent=4)	

def runFragRDT(workDir, inDir, outDir, rdtInFile, disasterFiles, fragInFile, fragOut, rdtOutFile, toSkip, debug=False):
	''' Run fragility and RDT.
	'''
	if 'fragility' not in toSkip:
		# Run micot-fragility.
		setFragInputFiles(inDir, fragInFile, disasterFiles)
		command = 'java -jar '+pJoin(workDir,'bin','SimpleFragilityEngine_0.3.jar')+' '+pJoin('inData',fragInFile)+' '+pJoin(outDir,fragOut)
		proc = subprocess.Popen([command], stdout=subprocess.PIPE, shell=True)
		(out, err) = proc.communicate()
		print "Running Fragility:\n", out

		# Place results into RDT input.
		# Read files.
		with open(pJoin(outDir,fragOut), "r") as jsonIn:
			fragContents = json.load(jsonIn)
		with open(pJoin(inDir,rdtInFile), "r") as jsonIn:
			rdtContents = json.load(jsonIn)
		# Get damaged lines.
		line_list = []
		for damage in fragContents:
			# Find line/nodes to disable based on presence in to be damages file.
			if float(damage['value']) > random.random():
				for key, values in rdtContents.items():
					if key == "lines":
						for item in values:
							if item["node1_id"] == damage['assetID'] or \
							   item["node2_id"] == damage['assetID']:
								if item["id"] not in line_list:
									line_list.append(item["id"])
		for key, values in rdtContents.items():
			if key == "scenarios":
				values[0]["disable_lines"] = line_list
		# Write to rdt file.
		with open(pJoin(inDir,rdtInFile), "w") as outFile:
			json.dump(rdtContents, outFile, indent=4)	
		print "Sent damage scenarios to RDT file."

	# Run micot-rdt.
	if debug:
		print "Running RDT..."
		print "************************************"
	os.chdir("bin/micot-application-rdt")
	command = 'java -classpath ,:micot-rdt.jar:../micot-libraries/jars/jna-4.1.0.jar:../micot-libraries/jars/jung-visualization-2.0.jar:../micot-libraries/jars/jung-samples-2.0.jar:../micot-libraries/jars/jung-jai-samples-2.0.jar:../micot-libraries/jars/jung-jai-2.0.jar:../micot-libraries/jars/jung-io-2.0.jar:../micot-libraries/jars/jung-graph-impl-2.0.jar:../micot-libraries/jars/jung-api-2.0.jar:../micot-libraries/jars/jung-api-2.0-tests.jar:../micot-libraries/jars/jung-algorithms-2.0.jar:../micot-libraries/jars/jung-3d-demos-2.0.jar:../micot-libraries/jars/javax.json-1.0.4.jar:../micot-libraries/jars/javax.json-api-1.0.jar:../micot-libraries/jars/jung-3d-2.0.jar gov.lanl.micot.rdt.exec.RunLPNorm -c ../../inData/'+rdtInFile+' -e ../../outData/'+rdtOutFile
	proc = subprocess.Popen([command], stdout=subprocess.PIPE, shell=True)
	(out, err) = proc.communicate()
	# Format output feeder.
	with open(pJoin(outDir,rdtOutFile), "r") as jsonIn:
		rdtOut = json.load(jsonIn)
	with open(pJoin(outDir, rdtOutFile),"w") as outFile:
		json.dump(rdtOut, outFile, indent = 4)
	if debug: 
		# print "\n\nOUTPUT:\n", out
		# print "\n\nERROR:\n", err
		print "\nOutput saved to:               %s"%(pJoin(outDir, rdtOutFile))
		print "************************************\n\n"

def dogridlabD(workDir, inDir, feederName, debug):
	# ... Steps here.
	# Run gridlabd.
	if debug:
		print "Running gridlabD..."
		print "************************************"
	# 1. Run gridlabD on circuit.
	feederJson = json.load(open(pJoin(inDir,feederName)))
	tree = feederJson.get("tree",{})
	attachments = feederJson.get("attachments",{})
	# 2. Read output.
	if debug:
		print "DID NOT RUN gridlabD. Results saved to:                 %s"%("N/A")
		print "************************************\n\n"
	return feederJson

def genDiagram(outDir, feederJson, debug):
	if debug:
		print "Generating Feeder plot..."
		print "************************************"
	links = feederJson.get("links",{})
	tree = feederJson.get("tree", {})
	toRemove = []
	for link in links:
		for typeLink in link.keys():
			if typeLink in ['source', 'target']:
				for key in link[typeLink].keys():
					if key in ['x', 'y']:
						objName = link[typeLink]['name']
						for x in tree:
							leaf = tree[x]
							if leaf.get('name','')==objName:
								if key=='x': leaf['latitude'] = link[typeLink][key]
								else: leaf['longitude'] = link[typeLink][key]
							elif 'config' in leaf.get('object','') or 'climate' in leaf.get('object','') or 'conductor' in leaf.get('object','') or 'solver_method' in leaf or 'omftype' in leaf or 'clock' in leaf or 'module' in leaf:
								if x not in toRemove: toRemove.append(x)
	for rem in toRemove: tree.pop(rem)
	nxG = feeder.treeToNxGraph(tree)
	feeder.latLonNxGraph(nxG) # This function creates a .plt reference which can be saved here.
	plt.savefig(pJoin(outDir,"feederChart.png"))
	if debug:
		print "Plot saved to:                 %s"%(pJoin(outDir,"feederChart.png"))
		print "************************************\n\n"

def writeHTMLTemplate(workDir, fragOut, rdtOut, displayWeb=True, debug=False):
	if debug:
		print "Generating HTML output..."
		print "************************************"
	f = open(pJoin(workDir, 'lpnorm_output.html'),'w')
	message = """<html>
		<head>
			<style type="text/css">
				.wrapper{
					float: left;
					width: 50%;
					height: 90%;
					position: relative;
				}
				#feederDiagram{ 
					width: 100%;
					height: 75%;
				}
				#damageSummary{
					width: 100%;
					height: 25%;
				}
				#rdtSummary{
					width: 100%;
					height: 100%;
				}
				#powerflowCheck{
					position: absolute;
					z-index: 10;
					bottom: 0;
					right: 0;
					background-color: red;
				}
			</style>
		</head>
		<body>
			<p style="font-size:40pt;text-align:center;margin:10 10 10 10;">RDT-Fragility OMF Integration</p>
			<div class ='wrapper'>
				<div id = "feederDiagram">
					<p style="text-align:center;margin:0 0 -12 0;">Feeder Diagram</p>
					<br>
					<img src="outData/feederChart.png" alt="Feeder Diagram">
				</div>
				<div id = "damageSummary">
					<p style="text-align:center;margin:0 0 -12 0;">Fragility Input JSON</p>
					<br>
					<iframe style="width:95%;" src="inData/fragOutString"></iframe>
				</div>
			</div>
			<div class="wrapper">
				<div id = "rdtSummary">
					<p style="text-align:center;margin:0 0 -12 0;">RDT Output JSON</p>
					<br>
					<iframe style="width:95%;height:94%;" src="outData/rdtOutputString"></iframe>
				</div>
				<!--<div id = "powerflowCheck">
					Power Check Failed
				</div>-->
			</div>
		</body>
	</html>"""
	message = message.replace('fragOutString',fragOut)
	message = message.replace('rdtOutputString',rdtOut)
	f.write(message)
	f.close()
	if displayWeb: 
		webbrowser.open_new_tab("file://" + pJoin(workDir,"lpnorm_output.html"))
	if debug:
		print "\nSaved to:               %s"%(pJoin(workDir, 'lpnorm_output.html'))
		print "************************************\n\n"	

# Tests.
def _tests(feederName=None, otherVars={}, testCase=0, debug=False, displayWeb=False):
	# Setup environment and paths. 
	workDir = os.getcwd()
	inDir = pJoin(workDir,'inData')
	outDir = pJoin(workDir,'outData')
	if not os.path.exists(outDir):
		os.makedirs(outDir)

	# Select a case for Frag/RDT.
	if testCase==0:
		# Take in user input.
		inData =  json.load(open(pJoin(inDir,otherVars)))
		disable = ['fragility']
		rdtInFile = convertToRDT(inData, inDir, feederName, debug)
		fragInFile = convertToFrag(inData, inDir, feederName, debug)
		disasterFiles = {'Windspeed' : 'WindArcTestGridTrevor.asc'}
		fragOut = 'fragOutput'+feederName.strip('omd')+'json'
		rdtOutFile = 'rdtOutput'+feederName.strip('omd')+'json'
	else:
		inData = {
			'phase_variation' : 0.15, 
			'chance_constraint' : 1.0,
			'critical_load_met' : 0.98,
			'total_load_met' : 0.5
		}
		if testCase==1:
			# Case 1: Trevor example.
			print "Running trevor example."
			disable = ['nada']
			rdtInFile = 'rdtInTrevor.json'
			disasterFiles = {'Windspeed' : 'WindArcTestGridTrevor.asc'}
			fragInFile = 'fragInTrevor.json'
			fragOut = 'fragOutputTrevor.json'
			rdtOutFile = 'rdtOutputTrevor.json'	
		elif testCase==2:
			# Case 2: Simple market system.
			print "Running simple market system example."
			disable = ['fragility']
			feederName = 'Simple_Market_System.omd'
			rdtInFile = convertToRDT(inData, inDir, feederName, debug)
			fragInFile = convertToFrag(inData, inDir, feederName, debug)
			disasterFiles = {'Windspeed' : 'WindArcTestGridTrevor.asc'}
			fragOut = 'fragOutput'+feederName.strip('omd')+'json'
			rdtOutFile = 'rdtOutput'+feederName.strip('omd')+'json'
		elif testCase==3:
			# Case 3: Julia files.
			print "Not complete: Julia example with 34 bus."
			disasterFiles = {'IceThickness':'IceArcTestGrid.asc','Windspeed':'WindArcTestGrid.asc'}

	# Run Fragility & RDT.
	runFragRDT(workDir, inDir, outDir, rdtInFile, disasterFiles, fragInFile, fragOut, rdtOutFile, disable, debug)

	# Create GLM and run gridlabD.
	feederJson = dogridlabD(workDir, inDir, feederName, debug)

	# Graph feeder.
	genDiagram(outDir, feederJson, debug)

	# Create HTML page of results.
	writeHTMLTemplate(workDir, fragInFile, rdtOutFile)
	print "Wrote file %s"%(pJoin(workDir, 'lpnorm_output.html'))

if __name__=='__main__':
	if len(sys.argv) == 1:
		# Pick a test case 1-3.
		_tests(testCase=2, debug=True)		
	elif len(sys.argv) == 3:
		# Run user specified example.
		_tests(feederName=sys.argv[1], otherVars=sys.argv[2])
	elif len(sys.argv) == 4:
		# Run user specified example.
		print "Running with debugging enabled (level %s)"%(str(sys.argv[3]))
		_tests(feederName=sys.argv[1], otherVars=sys.argv[2], debug=sys.argv[3])
	else:
		print "Sorry only the following arguments are supported: feederName vars.json debug=True|False"

'''TODO: 
	XXX Simplify object creation to required elems only.
	XXX Fix line_code x/rmatrix reaading. Assign ones wih correct # of phases.
	XXX Ask David then Russel:
		What are the S/N phases? N = neutral, S = neutral for split phase (120V).
		Are all the other elements for bus required:# min, max_voltage, y, x, has_generator, has_phase, ref_voltage. No. Russel updated the default behavior in v4.
		Loads: is_critical required? Not required.
		What are generators? Solar or generators on the circuit itself? Answered by David in email.
	XXX Ask LANL: Update schema: What are required fields for inputs? Schemas updated. 
	OOO Create layout for rest of integration: chart gen., html template creation, etc.
	OOO Convert feeder to fragility format. 
	OOO Run fragility and put scenarios into RDT.
	OOO Reg is a line; Make regulator a bus and make lines to it?
	OOO How do I calculate reactive_phase/real_phases? Has to do with power.
	OOO	Put in formula for harden_cost.
	OOO Check Super model visually and textually: Are triplex_meters sufficient for a load? Don't include houses?
	OOO Get in accurate data for: line capacity, num_poles, 
'''