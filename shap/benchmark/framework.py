import matplotlib.pyplot as plt 
import pandas as pd 
import numpy as np 
import itertools as it 
import sklearn 
import shap 
from sklearn.model_selection import train_test_split
from shap.utils import safe_isinstance, MaskedModel
from shap.benchmark import SequentialPerturbation

def update(model, X, y, explainer, masker, sort_order, score_function, perturbation, scores):
    metric = perturbation + ' ' + sort_order
    sp = SequentialPerturbation(model, masker, sort_order, score_function, perturbation)
    x, y, auc = sp.score(explainer, X, y=y)
    scores['metrics'].append(metric)
    scores['values'][metric] = [x, y, auc] 

def get_benchmark(model, X, y, explainer, masker, metrics, exp_num=1, *args):
    # convert dataframes
    if safe_isinstance(X, "pandas.core.series.Series") or safe_isinstance(X, "pandas.core.frame.DataFrame"):
        X = X.values
    if safe_isinstance(masker, "pandas.core.series.Series") or safe_isinstance(masker, "pandas.core.frame.DataFrame"):
        masker = masker.values
    
    # in case the explainer doesn't have a name
    try: 
        name = explainer.name 
    except: 
        name = 'explainer' + str(exp_num) 
        exp_num += 1 

    # record scores per metric 
    scores = {'name': name, 'metrics': list(), 'values': dict()}
    for sort_order, perturbation in list(it.product(metrics['sort_order'], metrics['perturbation'])):
        score_function = lambda true, pred: np.mean(pred)
        update(model, X, y, explainer, masker, sort_order, score_function, perturbation, scores)

    return scores 

def get_metrics(benchmarks, selection):
    # select metrics to plot using selection function
    explainer_metrics = set()
    for explainer in benchmarks: 
        scores = benchmarks[explainer]
        if len(explainer_metrics) == 0: 
            explainer_metrics = set(scores['metrics'])
        else: 
            explainer_metrics = selection(explainer_metrics, set(scores['metrics']))
    
    return list(explainer_metrics)

def trend_plot(benchmarks):
    explainer_metrics = get_metrics(benchmarks, lambda x, y: x.union(y))

    # plot all curves if metric exists 
    for metric in explainer_metrics:
        plt.clf()

        for explainer in benchmarks: 
            scores = benchmarks[explainer]
            if metric in scores['values']:
                x, y, auc = scores['values'][metric]
                plt.plot(x, y, label='{} - {}'.format(round(auc, 3), explainer))

        metric_passive = ''
        if 'keep' in metric: 
            metric_passive = 'Kept'
        if 'remove' in metric:
            metric_passive = 'Removed'

        plt.ylabel('Mean Model Output')
        plt.xlabel('Max Fraction of Features {}'.format(metric_passive))
        plt.title(metric)
        plt.legend()
        plt.show()
    
def compare_plot(benchmarks):
    explainer_metrics = get_metrics(benchmarks, lambda x, y: x.intersection(y))
    explainers = list(benchmarks.keys())
    num_explainers = len(explainers)
    num_metrics = len(explainer_metrics)

    # dummy start to evenly distribute explainers on the left 
    # can later be replaced by boolean metrics 
    aucs = dict()
    for i in range(num_explainers): 
        explainer = explainers[i]
        aucs[explainer] = [i/(num_explainers-1)] 
    
    # normalize per metric
    for metric in explainer_metrics: 
        max_auc, min_auc = -float('inf'), float('inf')

        for explainer in explainers: 
            scores = benchmarks[explainer] 
            _, _, auc = scores['values'][metric]
            min_auc = min(auc, min_auc)
            max_auc = max(auc, max_auc)
        
        for explainer in explainers: 
            scores = benchmarks[explainer] 
            _, _, auc = scores['values'][metric]
            aucs[explainer].append((auc-min_auc)/(max_auc-min_auc))
    
    # plot common curves
    ax = plt.gca()
    for explainer in explainers: 
        plt.plot(np.linspace(0, 1, len(explainer_metrics)+1), aucs[explainer], '--o')

    ax.tick_params(which='major', axis='both', labelsize=8)

    ax.set_yticks([i/(num_explainers-1) for i in range(0, num_explainers)])
    ax.set_yticklabels(explainers, rotation=0)

    ax.set_xticks(np.linspace(0, 1, num_metrics+1))
    ax.set_xticklabels([' '] + explainer_metrics, rotation=45, ha='right')

    plt.grid(which='major', axis='x', linestyle='--')
    plt.tight_layout()
    plt.ylabel('Relative Performance of Each Explanation Method')
    plt.xlabel('Evaluation Metrics')
    plt.title('Explanation Method Performance Across Metrics')
    plt.show()