from shap.utils import safe_isinstance, MaskedModel
import shap.links
import shap.datasets
import matplotlib.pyplot as pl
import sklearn
import numpy as np
from tqdm.auto import tqdm
import time


class SequentialPerturbation():
    def __init__(self, f, masker, sort_order, score_function, perturbation):
        self.f = f
        self.masker = masker
        self.sort_order = sort_order
        self.score_function = score_function
        self.perturbation = perturbation
        
        # convert dataframe
        if safe_isinstance(self.masker, "pandas.core.series.Series") or safe_isinstance(self.masker, "pandas.core.frame.DataFrame"):
            self.masker = self.masker.values

        # If the user just gave a dataset as the masker
        # then we make a masker that perturbs features independently
        if type(self.masker) == np.ndarray:
            self.masker_data = self.masker
            self.masker = lambda mask, x: x * mask + self.masker_data * np.invert(mask)
        
        # define our sort order
        if self.sort_order == "positive":
            self.sort_order_map = lambda x: np.argsort(-x)
        elif self.sort_order == "negative":
            self.sort_order_map = lambda x: np.argsort(x)
        elif self.sort_order == "absolute":
            self.sort_order_map = lambda x: np.argsort(-abs(x))
        else:
            raise ValueError("sort_order must be either \"positive\", \"negative\", or \"absolute\"!")
            
        self.score_values = []
        self.score_aucs = []
        self.labels = []

    def maskedmodel(self):
        self.masked_model = MaskedModel(self.f, self.masker, shap.links.identity) 
    
    def score(self, explainer, X, y=None, label=None, silent=False):
        # if explainer is already the attributions
        # TODO: I changed this for text input, but it breaks for tabular data, please check, should be simple fix
        if safe_isinstance(explainer, "numpy.ndarray"): 
            attributions = explainer 
        else: 
            attributions = explainer(X).values
        
        if label is None:
            label = "Score %d" % len(self.score_values)
        
        # convert dataframes
        if safe_isinstance(X, "pandas.core.series.Series") or safe_isinstance(X, "pandas.core.frame.DataFrame"):
            X = X.values
            
        # convert all single-sample vectors to matrices
        if not hasattr(attributions[0], "__len__"):
            attributions = np.array([attributions])
        if not hasattr(X[0], "__len__"):
            X = np.array([X])
        
        # loop over all the samples
        pbar = None
        start_time = time.time()
        svals = []

        for i in range(len(X)):

            # TODO: Infering input length depends on data type, simplest is calling masker.shape (function or attribute)
            # If masked does not have a shap funtion we can try to infer from attribution matrix (might get tricky for image data)

            if callable(self.masker):
                mshape = self.masker.shape(X[i])[1]
            else:
                mshape = self.masker.shape


            # TODO: For image data, we need to sort (x,y,channel) indices by the corresponding shap values and mask/unmask

            mask = np.ones(mshape, dtype=np.bool) * (self.perturbation == "remove")
            ordered_inds = self.sort_order_map(attributions[i])
            
            # compute the fully masked score
            values = np.zeros(mshape+1)
            masked = self.masker(mask, X[i])
            values[0] = self.f(masked).mean(0)
            
            # TODO: For data sets with multiple outputs loop over the output samples and order based on corresponding attributions, 
            # TODO: For this, need to experiment with micro average (average sub-sample values for every sample) or macro average  (collect all sub-sample values and average at the end)
            # default curr_val to be fully masked score in case when entire attributions is negative/positive
            # avoid nan by setting default curr_val to full masked score
            curr_val = self.f(masked).mean(0)
            for j in range(mshape):
                oind = ordered_inds[j]
                
                # keep masking our inputs until there are none more to mask
                if not ((self.sort_order == "positive" and attributions[i][oind] <= 0) or \
                        (self.sort_order == "negative" and attributions[i][oind] >= 0)):
                    mask[oind] = self.perturbation == "keep"
                    masked = self.masker(mask, X[i])
                    curr_val = self.f(masked).mean(0)
                values[j+1] = curr_val
            svals.append(values)

            if pbar is None and time.time() - start_time > 5:
                pbar = tqdm(total=len(X), disable=silent, leave=False)
                pbar.update(i+1)
            if pbar is not None:
                pbar.update(1)
        if pbar is not None:
            pbar.close()
            
        self.score_values.append(np.array(svals))
        
        if self.sort_order == "negative": 
            curve_sign = -1
        else: 
            curve_sign = 1

        svals = np.array(svals)
        #scores = [self.score_function(y, svals[:,i]) for i in range(svals.shape[1])]
        #auc = sklearn.metrics.auc(np.linspace(0, 1, len(scores)), curve_sign*(scores-scores[0]))
        auc = 0

        self.labels.append(label)
        
        xs = np.linspace(0, 1, 100)
        curves = np.zeros((len(self.score_values[-1]), len(xs)))
        for j in range(len(self.score_values[-1])):
            xp = np.linspace(0, 1, len(self.score_values[-1][j]))
            yp = self.score_values[-1][j]
            curves[j,:] = np.interp(xs, xp, yp)
        ys = curves.mean(0)

        auc = sklearn.metrics.auc(np.linspace(0, 1, len(ys)), curve_sign*(ys-ys[0]))
        
        return xs, ys, auc
        
    def plot(self):
        
        for i in range(len(self.score_values)):
            xs = np.linspace(0, 1, 100)
            curves = np.zeros((len(self.score_values[i]), len(xs)))
            for j in range(len(self.score_values[i])):
                xp = np.linspace(0, 1, len(self.score_values[i][j]))
                yp = self.score_values[i][j]
                curves[j,:] = np.interp(xs, xp, yp)
            ys = curves.mean(0)
            pl.plot(xs, ys, label=self.labels[i] + " AUC %0.4f" % self.score_aucs[i].mean())
        if (self.sort_order == "negative") != (self.perturbation == "remove"):
            pl.gca().invert_yaxis()
        pl.legend()
        pl.show()