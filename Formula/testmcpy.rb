class Testmcpy < Formula
  include Language::Python::Virtualenv

  desc "MCP Testing Framework - Test LLM tool calling with MCP services"
  homepage "https://github.com/preset-io/testmcpy"
  url "https://files.pythonhosted.org/packages/8e/22/6cbba435a69025393d52d233f333a5d35bdff4fe247af1d3efd57e756974/testmcpy-0.11.22.tar.gz"
  sha256 "f497f9ee4b3751e25453db34a7cc26d7162bf0124e644e896707dc3e60064947"
  license "Apache-2.0"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "MCP Testing Framework", shell_output("#{bin}/testmcpy --help")
  end
end
