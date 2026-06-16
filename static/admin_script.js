function createRecipeResult(image, text, title, parentContainer) {
    var imgEl = document.createElement("img");
    imgEl.src = image

    var textEl = document.createElement("p");
    textEl.innerText = text

    var titleEl = document.createElement("h1");
    titleEl.innerText = title

    var recipeEl = document.createElement("div");
    recipeEl.className = "recipe"

    var recipeGroupEl = document.createElement("div");
    recipeGroupEl.className = "recipe-group"

    var recipeImgEl = document.createElement("div");
    recipeImgEl.className = "recipe-img"
    recipeImgEl.appendChild(imgEl)


    recipeGroupEl.appendChild(titleEl);
    recipeGroupEl.appendChild(textEl);

    recipeEl.appendChild(recipeImgEl);
    recipeEl.appendChild(recipeGroupEl)

    parentContainer.appendChild(recipeEl)
}

function fetchData(formData, error) {
     fetch("http://localhost:8081/api/v1/search", {
            method:"POST",
            body: formData
        })
        .then(async (resp) => {
            if(!resp.ok) {
                container.appendChild(error)
                console.error(resp)
                var err = await resp.json()
                console.error(err)
                throw err
            }

            error.remove()
            return await resp.json()
        })
        .then(data => {
            console.log(data)
            results.innerHTML = ""
            data.forEach(r => {
//                var imgEl = document.createElement("img");
//                imgEl.src = r.image_path
//                var textEl = document.createElement("p");
//                textEl.innerText = r['text']
//                results.appendChild(imgEl);
//                results.appendChild(textEl);
                createRecipeResult(r.image_path, r['text'], r['title'], results)
            })
        })
        .catch(err => {
            if (err instanceof TypeError) {
                error.innerText = "Connection problem, try again. "
                return
            }
            console.error(err)
            error.innerText = err.detail
        })
}

document.addEventListener("DOMContentLoaded", () => {

    var formReset = document.getElementById("reset-btn")
    var submittedFile = document.querySelector("input[type='file']")
    var previewImg = document.getElementById("preview")
    var settingsForm = document.getElementById("settings")
    var settingsError = document.getElementById("settings-error")

    var recipeError = document.getElementById("recipe-error")
    var recipeForm = document.getElementById("recipe_form")
    if (settingsForm){
    settingsForm.addEventListener("submit", (e) => {
        e.preventDefault()

        updateSettings(settingsForm, settingsError)
    })}

    recipeForm.addEventListener("submit", (e) => {
        e.preventDefault()
        var form = new FormData(recipeForm);
        createRecipe(form, recipeForm, recipeError);
    })

    submittedFile.addEventListener("change", () => {
    const [file] = submittedFile.files
       console.log(submittedFile)
       if (file) {
        previewImg.src = URL.createObjectURL(file)
        previewImg.style.display = "block"
       }
    })

    formReset.addEventListener("click", () => {
        uploadForm.reset()
       previewImg.src = ""

        results.innerText = ""
    })

})
function updateSettings(settingsForm, recipeError) {

    formData =new FormData(settingsForm)

    data = {
        alpha: parseFloat(formData.get('alpha')),
        retrieval_size: parseInt(formData.get("retrieval_size")),
        reranking:  document.getElementById('rerank').checked
    }
    fetch("http://localhost:8081/api/v1/settings", {
        method: "PATCH",
        body: JSON.stringify(data),
        headers: {
            "content-type": "application/json"
        }
    }).then(async resp => {
        if (!resp.ok) {
            var err = await resp.json()
            throw err
        }

        window.location.href = "/admin"
    })
    .catch(err => {
        if (err.detail) {
            recipeError.innerHTML = err.detail
        } else {
            recipeError.innerHTML = "Something went wrong"
        }

        console.error(err)
    })

}

function createRecipe(formData, recipeForm, recipeError) {
    fetch("http://localhost:8081/api/v1/recipes", {
        method: "POST",
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
        if (err.detail) {
            recipeError.innerHTML = err.detail
        } else {
            recipeError.innerHTML = "Something went wrong"
        }

        console.error(err)
    })
}