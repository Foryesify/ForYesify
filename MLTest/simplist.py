import torch.nn as nn
import torch.optim as optim
import torch

class MyNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc_layer = nn.Linear(2, 10)
    def forward(self, data):
        return self.fc_layer(data)

net = MyNN()
print(net)

my_input = torch.tensor([1.0, 2.0])
my_target = torch.tensor([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

criterion = nn.MSELoss()
optimizer = optim.Adam(net.parameters(), lr=0.0001)

for epoch in range(100000):
    optimizer.zero_grad()
    output = net(my_input)
    loss = criterion(output, my_target)
    loss.backward()
    optimizer.step()
    if (epoch % 100 == 0):
        print(f"{epoch} : Loss {loss.item():.2f}")

print("\nTrained OK")
with torch.no_grad():
    final_output = net(my_input)

# 改这里：目标保留两位小数
print("Target:", [f"{x:.2f}" for x in my_target.numpy()])
# 改这里：预测保留两位小数
print("Fact:  ", [f"{x:.2f}" for x in final_output.numpy()])
