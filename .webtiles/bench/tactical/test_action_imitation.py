import unittest
import torch
from train_action_imitation import imitation_loss


class ToyPolicy:
    def __init__(self):
        self.logits = torch.zeros(3, requires_grad=True)

    def get_distribution(self, observations, action_masks):
        return torch.distributions.Categorical(
            logits=self.logits.expand(len(observations), -1).masked_fill(~action_masks, -1e8))


class ImitationTests(unittest.TestCase):
    def test_masked_likelihood_and_gradient(self):
        policy = ToyPolicy()
        loss = imitation_loss(policy, torch.zeros(1, 2),
                              torch.tensor([[True, False, True]]), torch.tensor([2]))
        self.assertAlmostEqual(loss.item(), 0.693147, places=5)
        loss.backward()
        self.assertEqual(policy.logits.grad[1].item(), 0)
        self.assertLess(policy.logits.grad[2].item(), 0)

    def test_reject_illegal_teacher_label(self):
        with self.assertRaisesRegex(ValueError, 'Illegal demonstration'):
            imitation_loss(ToyPolicy(), torch.zeros(1, 2),
                           torch.tensor([[True, False, True]]), torch.tensor([1]))


if __name__ == '__main__':
    unittest.main()
