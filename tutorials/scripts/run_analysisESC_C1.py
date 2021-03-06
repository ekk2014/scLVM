import h5py
import sys
sys.path.append('./')
sys.path.append('../CFG')
sys.path.append('../include')
#limix_path = '/Users/florian/Code/python_code/limix-master/build/release.darwin/interfaces/python'
#sys.path.append(limix_path)
sys.path.append('./..')
import limix.modules.panama as PANAMA
import limix.modules.varianceDecomposition as VAR
import limix.modules.qtl as QTL
from include.utils import dumpDictHdf5
import scipy as SP
import limix
import limix.modules.varianceDecomposition as VAR
import pdb
#sys.path.append('../scLVM')
from scLVM import scLVM
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import pylab as PL




if __name__ == '__main__':
	from ESC_C1 import *

	#Either distribute over several jobs 
	#(recommended when performing correlation analyis) or not (debug mode)
	if 'debug' in sys.argv:
		Njobs = 1
		ijob  = 0
	else:
		Njobs = int(sys.argv[1])
		ijob  = int(sys.argv[2])-1
	
	#Where to save results	
	out_name = 'correlation_test'
	out_dir  = os.path.join(CFG['out_base'],out_name)
	run_dir  = os.path.join(out_dir,'runsESCs')

	if not os.path.exists(run_dir):
		os.makedirs(run_dir)

	#load data
	f = h5py.File(CFG['data_file'],'r')
	Y=f['LogNcountsMmus'][:]
	Y = f['LogNcountsMmus'][:]				 # gene expression matrix
	tech_noise = f['LogVar_techMmus'][:]	   # technical noise
	genes_het_bool=f['genes_heterogen'][:]	 # index of heterogeneous(??!??) genes
	geneID = f['sym_names'][:]			# gene names
	cellcyclegenes_filter = SP.unique(f['cellcyclegenes_filter'][:].ravel() -1) # idx of cell cycle genes
	cellcyclegenes_filterCB600 = f['ccCBall_gene_indices'][:].ravel() -1		# idxof cell cycle genes ...
	#ground truth from Hoechst staining
	phase_vec = f['labels'][:].ravel()
	if max(phase_vec)==4:
		phase_vec[phase_vec==1]=2
		phase_vec = phase_vec-1

	KG1 = SP.zeros((Y.shape[0],Y.shape[0]))
	for iph in range(Y.shape[0]):
		for jph in range(Y.shape[0]):
			if SP.bitwise_and(phase_vec[iph]==phase_vec[jph], phase_vec[iph]==1):
				KG1[iph,jph]=1

	KS = SP.zeros((Y.shape[0],Y.shape[0]))
	for iph in range(Y.shape[0]):
		for jph in range(Y.shape[0]):
			if SP.bitwise_and(phase_vec[iph]==phase_vec[jph], phase_vec[iph]==2):
				KS[iph,jph]=1

	KG2M = SP.zeros((Y.shape[0],Y.shape[0]))
	for iph in range(Y.shape[0]):
		for jph in range(Y.shape[0]):
			if SP.bitwise_and(phase_vec[iph]==phase_vec[jph], phase_vec[iph]==3):
				KG2M[iph,jph]=1

	#intra-phase variations in cell size
	sfCellSize = SP.log10(f['ratioEndo'][:])
	sfCellSize -= sfCellSize.mean()
	sfCellSize = sfCellSize.reshape(1,sfCellSize.shape[0])
	Ksize = SP.dot(sfCellSize.transpose(), sfCellSize)
	Ksize /= Ksize.diagonal().mean() 

	# filter cell cycle genes
	idx_cell_cycle = SP.union1d(cellcyclegenes_filter,cellcyclegenes_filterCB600)
	Ymean2 = Y.mean(0)**2>0
	idx_cell_cycle_noise_filtered = SP.intersect1d(idx_cell_cycle,SP.array(SP.where(Ymean2.ravel()>0)))
	Ycc = Y[:,idx_cell_cycle_noise_filtered]
	
	#Fit GPLVM to data 
	k = 1					 # number of latent factors
	file_name = CFG['panama_file']# name of the cache file
	recalc = True # recalculate X and Kconf
	sclvm = scLVM(Y)
	pdb.set_trace()
	X,Kcc,varGPLVM = sclvm.fitGPLVM(idx=idx_cell_cycle_noise_filtered,k=1,out_dir='./cache',file_name=file_name,recalc=recalc)

	#3. load relevant dataset for analysis
	genes_het=SP.array(SP.where(f['genes_heterogen'][:].ravel()==1))
	tech_noise=f['LogVar_techMmus'][:]

   # considers only heterogeneous genes
	Ihet = genes_het_bool==1
	Y	= Y[:,Ihet]
	tech_noise = tech_noise[Ihet]
	geneID = geneID[Ihet] 
	
	
	#4. split across genes
	Iy	= SP.array(SP.linspace(0,Y.shape[1],Njobs+1),dtype='int')
	i0	= Iy[ijob]
	i1	= Iy[ijob+1]

	#create outfile
	out_file = os.path.join(run_dir,'job_%03d_%03d.hdf5' % (ijob,Njobs))
	fout	 = h5py.File(out_file,'w')
	
	#ground truth
	#KList = {}
	#KList[0] = KG1
	#KList[1] = KS
	#KList[2] = KG2M

	sclvm = scLVM(Y,geneID=geneID,tech_noise=tech_noise)

	# fit the model from i0 to i1
	sclvm.varianceDecomposition(K=Kcc,i0=i0,i1=i1) 
	normalize=True	# variance components are normalizaed to sum up to one

	# get variance components
	var, var_info = sclvm.getVarianceComponents(normalize=normalize)
#	var_filtered = var[var_info['conv']] # filter out genes for which vd has not converged

	# get corrected expression levels
	Ycorr = sclvm.getCorrectedExpression()
	
	# fit lmm without correction
	pv0,beta0,info0 = sclvm.fitLMM(K=None,i0=i0,i1=i1,verbose=True)
	# fit lmm with correction
	pv,beta,info = sclvm.fitLMM(K=Kcc,i0=i0,i1=i1,verbose=True)
	
	#write to file
	count = 0
	for i in xrange(i0,i1):
		gene_id = 'gene_%d' % (i)
		out_group = fout.create_group(gene_id)
		RV = {}
		RV['pv0'] = pv0[count,:]
		RV['pv'] = pv[count,:]
		RV['beta'] = beta[count,:]
		RV['beta0'] = beta0[count,:]
		RV['vars'] = var[count,:]
		RV['varsnorm'] = var[count,:]
		RV['is_converged']=SP.repeat(var_info['conv'][count]*1,5)
		RV['Ycorr'] = Ycorr[:,count]
		dumpDictHdf5(RV,out_group)
		count+=1
	fout.close()
		 
	
