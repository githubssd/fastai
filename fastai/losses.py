# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01a_losses.ipynb.

# %% ../nbs/01a_losses.ipynb 2
from __future__ import annotations
from .imports import *
from .torch_imports import *
from .torch_core import *
from .layers import *

# %% auto 0
__all__ = ['BaseLoss', 'CrossEntropyLossFlat', 'FocalLoss', 'FocalLossFlat', 'BCEWithLogitsLossFlat', 'BCELossFlat',
           'MSELossFlat', 'L1LossFlat', 'LabelSmoothingCrossEntropy', 'LabelSmoothingCrossEntropyFlat', 'DiceLoss']

# %% ../nbs/01a_losses.ipynb 5
class BaseLoss():
    "Same as `loss_cls`, but flattens input and target."
    activation=decodes=noops
    def __init__(self, 
        loss_cls, # Uninitialized PyTorch-compatible loss
        *args,
        axis:int=-1, # Class axis
        flatten:bool=True, # Flatten `inp` and `targ` before calculating loss
        floatify:bool=False, # Convert `targ` to `float`
        is_2d:bool=True, # Whether `flatten` keeps one or two channels when applied
        **kwargs
    ):
        store_attr("axis,flatten,floatify,is_2d")
        self.func = loss_cls(*args,**kwargs)
        self.func.__annotations__ = typing.get_type_hints(self.func, globalns=globals(), localns=locals()) # used to prevent unpicklable loss functions (https://github.com/fastai/fastai/issues/3901)
        functools.update_wrapper(self, self.func)
        
    def __repr__(self) -> str: return f"FlattenedLoss of {self.func}"
    
    @property
    def reduction(self) -> str: return self.func.reduction
    
    @reduction.setter
    def reduction(self, v:str):
        "Sets the reduction style (typically 'mean', 'sum', or 'none')" 
        self.func.reduction = v

    def _contiguous(self, x:Tensor) -> TensorBase:
        "Move `self.axis` to the last dimension and ensure tensor is contigous for `Tensor` otherwise just return"
        return TensorBase(x.transpose(self.axis,-1).contiguous()) if isinstance(x,torch.Tensor) else x

    def __call__(self, 
        inp:Tensor|MutableSequence, # Predictions from a `Learner`
        targ:Tensor|MutableSequence, # Actual y label
        **kwargs
    ) -> TensorBase: # `loss_cls` calculated on `inp` and `targ`
        inp,targ  = map(self._contiguous, (inp,targ))
        if self.floatify and targ.dtype!=torch.float16: targ = targ.float()
        if targ.dtype in [torch.int8, torch.int16, torch.int32]: targ = targ.long()
        if self.flatten: inp = inp.view(-1,inp.shape[-1]) if self.is_2d else inp.view(-1)
        return self.func.__call__(inp, targ.view(-1) if self.flatten else targ, **kwargs)
    
    def to(self, device:torch.device):
        "Move the loss function to a specified `device`"
        if isinstance(self.func, nn.Module): self.func.to(device)

# %% ../nbs/01a_losses.ipynb 8
@delegates()
class CrossEntropyLossFlat(BaseLoss):
    "Same as `nn.CrossEntropyLoss`, but flattens input and target."
    y_int = True # y interpolation
    @use_kwargs_dict(keep=True, weight=None, ignore_index=-100, reduction='mean')
    def __init__(self, 
        *args, 
        axis:int=-1, # Class axis
        **kwargs
    ): 
        super().__init__(nn.CrossEntropyLoss, *args, axis=axis, **kwargs)
    
    def decodes(self, x:Tensor) -> Tensor:    
        "Converts model output to target format"
        return x.argmax(dim=self.axis)
    
    def activation(self, x:Tensor) -> Tensor: 
        "`nn.CrossEntropyLoss`'s fused activation function applied to model output"
        return F.softmax(x, dim=self.axis)

# %% ../nbs/01a_losses.ipynb 13
class FocalLoss(Module):
    y_int=True # y interpolation
    def __init__(self, 
        gamma:float=2.0, # Focusing parameter. Higher values down-weight easy examples' contribution to loss
        weight:Tensor=None, # Manual rescaling weight given to each class
        reduction:str='mean' # PyTorch reduction to apply to the output
    ): 
        "Applies Focal Loss: https://arxiv.org/pdf/1708.02002.pdf"
        store_attr()
    
    def forward(self, inp:Tensor, targ:Tensor) -> Tensor:
        "Applies focal loss based on https://arxiv.org/pdf/1708.02002.pdf"
        ce_loss = F.cross_entropy(inp, targ, weight=self.weight, reduction="none")
        p_t = torch.exp(-ce_loss)
        loss = (1 - p_t)**self.gamma * ce_loss
        if self.reduction == "mean":
            loss = loss.mean()
        elif self.reduction == "sum":
            loss = loss.sum()
        return loss


class FocalLossFlat(BaseLoss):
    """
    Same as CrossEntropyLossFlat but with focal paramter, `gamma`. Focal loss is introduced by Lin et al. 
    https://arxiv.org/pdf/1708.02002.pdf. Note the class weighting factor in the paper, alpha, can be 
    implemented through pytorch `weight` argument passed through to F.cross_entropy.
    """
    y_int = True # y interpolation
    @use_kwargs_dict(keep=True, weight=None, reduction='mean')
    def __init__(self, 
        *args, 
        gamma:float=2.0, # Focusing parameter. Higher values down-weight easy examples' contribution to loss
        axis:int=-1, # Class axis
        **kwargs
    ):
        super().__init__(FocalLoss, *args, gamma=gamma, axis=axis, **kwargs)
        
    def decodes(self, x:Tensor) -> Tensor: 
        "Converts model output to target format"
        return x.argmax(dim=self.axis)
    
    def activation(self, x:Tensor) -> Tensor: 
        "`F.cross_entropy`'s fused activation function applied to model output"
        return F.softmax(x, dim=self.axis)

# %% ../nbs/01a_losses.ipynb 16
@delegates()
class BCEWithLogitsLossFlat(BaseLoss):
    "Same as `nn.BCEWithLogitsLoss`, but flattens input and target."
    @use_kwargs_dict(keep=True, weight=None, reduction='mean', pos_weight=None)
    def __init__(self, 
        *args, 
        axis:int=-1, # Class axis
        floatify:bool=True, # Convert `targ` to `float`
        thresh:float=0.5, # The threshold on which to predict 
        **kwargs
    ):
        if kwargs.get('pos_weight', None) is not None and kwargs.get('flatten', None) is True:
            raise ValueError("`flatten` must be False when using `pos_weight` to avoid a RuntimeError due to shape mismatch")
        if kwargs.get('pos_weight', None) is not None: kwargs['flatten'] = False
        super().__init__(nn.BCEWithLogitsLoss, *args, axis=axis, floatify=floatify, is_2d=False, **kwargs)
        self.thresh = thresh

    def decodes(self, x:Tensor) -> Tensor:
        "Converts model output to target format"
        return x>self.thresh
    
    def activation(self, x:Tensor) -> Tensor:
        "`nn.BCEWithLogitsLoss`'s fused activation function applied to model output"
        return torch.sigmoid(x)

# %% ../nbs/01a_losses.ipynb 18
@use_kwargs_dict(weight=None, reduction='mean')
def BCELossFlat(
    *args, 
    axis:int=-1, # Class axis
    floatify:bool=True, # Convert `targ` to `float`
    **kwargs
):
    "Same as `nn.BCELoss`, but flattens input and target."
    return BaseLoss(nn.BCELoss, *args, axis=axis, floatify=floatify, is_2d=False, **kwargs)

# %% ../nbs/01a_losses.ipynb 20
@use_kwargs_dict(reduction='mean')
def MSELossFlat(
    *args, 
    axis:int=-1, # Class axis
    floatify:bool=True, # Convert `targ` to `float`
    **kwargs
):
    "Same as `nn.MSELoss`, but flattens input and target."
    return BaseLoss(nn.MSELoss, *args, axis=axis, floatify=floatify, is_2d=False, **kwargs)

# %% ../nbs/01a_losses.ipynb 23
@use_kwargs_dict(reduction='mean')
def L1LossFlat(
    *args, 
    axis=-1, # Class axis
    floatify=True, # Convert `targ` to `float`
    **kwargs
):
    "Same as `nn.L1Loss`, but flattens input and target."
    return BaseLoss(nn.L1Loss, *args, axis=axis, floatify=floatify, is_2d=False, **kwargs)

# %% ../nbs/01a_losses.ipynb 24
class LabelSmoothingCrossEntropy(Module):
    y_int = True # y interpolation
    def __init__(self, 
        eps:float=0.1, # The weight for the interpolation formula
        weight:Tensor=None, # Manual rescaling weight given to each class passed to `F.nll_loss`
        reduction:str='mean' # PyTorch reduction to apply to the output
    ): 
        store_attr()

    def forward(self, output:Tensor, target:Tensor) -> Tensor:
        "Apply `F.log_softmax` on output then blend the loss/num_classes(`c`) with the `F.nll_loss`"
        c = output.size()[1]
        log_preds = F.log_softmax(output, dim=1)
        if self.reduction=='sum': loss = -log_preds.sum()
        else:
            loss = -log_preds.sum(dim=1) #We divide by that size at the return line so sum and not mean
            if self.reduction=='mean':  loss = loss.mean()
        return loss*self.eps/c + (1-self.eps) * F.nll_loss(log_preds, target.long(), weight=self.weight, reduction=self.reduction)

    def activation(self, out:Tensor) -> Tensor: 
        "`F.log_softmax`'s fused activation function applied to model output"
        return F.softmax(out, dim=-1)
    
    def decodes(self, out:Tensor) -> Tensor:
        "Converts model output to target format"
        return out.argmax(dim=-1)

# %% ../nbs/01a_losses.ipynb 27
@delegates()
class LabelSmoothingCrossEntropyFlat(BaseLoss):
    "Same as `LabelSmoothingCrossEntropy`, but flattens input and target."
    y_int = True
    @use_kwargs_dict(keep=True, eps=0.1, reduction='mean')
    def __init__(self, 
        *args, 
        axis:int=-1, # Class axis
        **kwargs
    ): 
        super().__init__(LabelSmoothingCrossEntropy, *args, axis=axis, **kwargs)
    def activation(self, out:Tensor) -> Tensor: 
        "`LabelSmoothingCrossEntropy`'s fused activation function applied to model output"
        return F.softmax(out, dim=-1)
    
    def decodes(self, out:Tensor) -> Tensor:
        "Converts model output to target format"
        return out.argmax(dim=-1)

# %% ../nbs/01a_losses.ipynb 30
class DiceLoss:
    "Dice loss for segmentation"
    def __init__(self, 
        axis:int=1, # Class axis
        smooth:float=1e-6, # Helps with numerical stabilities in the IoU division
        reduction:str="sum", # PyTorch reduction to apply to the output
        square_in_union:bool=False # Squares predictions to increase slope of gradients
    ):
        store_attr()
        
    def __call__(self, pred:Tensor, targ:Tensor) -> Tensor:
        "One-hot encodes targ, then runs IoU calculation then takes 1-dice value"
        targ = self._one_hot(targ, pred.shape[self.axis])
        pred, targ = TensorBase(pred), TensorBase(targ)
        assert pred.shape == targ.shape, 'input and target dimensions differ, DiceLoss expects non one-hot targs'
        pred = self.activation(pred)
        sum_dims = list(range(2, len(pred.shape)))
        inter = torch.sum(pred*targ, dim=sum_dims)        
        union = (torch.sum(pred**2+targ, dim=sum_dims) if self.square_in_union
            else torch.sum(pred+targ, dim=sum_dims))
        dice_score = (2. * inter + self.smooth)/(union + self.smooth)
        loss = 1- dice_score
        if self.reduction == 'mean':
            loss = loss.mean()
        elif self.reduction == 'sum':
            loss = loss.sum()
        return loss
    @staticmethod
    def _one_hot(
        x:Tensor, # Non one-hot encoded targs
        classes:int, # The number of classes 
        axis:int=1 # The axis to stack for encoding (class dimension)
    ) -> Tensor:
        "Creates one binary mask per class"
        return torch.stack([torch.where(x==c, 1, 0) for c in range(classes)], axis=axis)
    
    def activation(self, x:Tensor) -> Tensor: 
        "Activation function applied to model output"
        return F.softmax(x, dim=self.axis)
    
    def decodes(self, x:Tensor) -> Tensor:
        "Converts model output to target format"
        return x.argmax(dim=self.axis)
