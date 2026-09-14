import math
import unittest
import torch
from learner import distribution_diagnostics


class DiagnosticStabilityTests(unittest.TestCase):
    def test_underflow_does_not_make_kl_nan(self):
        p=torch.tensor([1000.,-1000.,0.])
        q=torch.tensor([-1000.,1000.,0.])
        kl,entropy=distribution_diagnostics(p,q)
        self.assertTrue(math.isfinite(kl))
        self.assertAlmostEqual(kl,2000.)
        self.assertAlmostEqual(entropy,0.)
        self.assertEqual(distribution_diagnostics(p,p),(0.,0.))

    def test_agrees_with_regular_kl(self):
        p=torch.tensor([1.,2.,3.],dtype=torch.float64)
        q=torch.tensor([2.,4.,1.],dtype=torch.float64)
        expected=torch.nn.functional.kl_div(q.log_softmax(-1),p.softmax(-1),reduction='sum')
        self.assertAlmostEqual(distribution_diagnostics(p,q)[0],float(expected))

    def test_bad_weights_are_not_hidden(self):
        with self.assertRaisesRegex(ValueError,'Non-finite'):
            distribution_diagnostics(torch.tensor([float('nan')]),torch.tensor([0.]))
