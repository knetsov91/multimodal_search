document.addEventListener("DOMContentLoaded", () => {
      var editForm = document.getElementById("recipe_edit_form")
      var error = document.getElementById("recipe-error")
      var preview = document.getElementById("preview")

      var submitFile = document.querySelector("input[type='file']")
      submitFile.addEventListener("change", () => {
        var [file] = submitFile.files
        if (file) {
            preview.src = URL.createObjectURL(file)
        }


      })
       preview.style.display = "block"
       editForm.addEventListener("submit", (e) => {
        e.preventDefault()
        var form = new FormData(editForm);
        editRecipe(form, editForm, error);
    })
})

function editRecipe(formData, recipeForm, recipeError) {
    var id = recipeForm.getAttribute("data-id")
    fetch("http://localhost:8081/api/v1/recipes/"+id, {
        method: "PATCH",
        body: formData
    })
    .then(async resp => {
        if (!resp.ok) {
            var err = await resp.json()
            throw err
        }
        recipeForm.reset()
        window.location.href = "/admin"
        console.log(await resp.js)
    console.log(resp)})
    .catch(err => {
                recipeError.innerHTML = "Error"
                console.error(err)
    })
}